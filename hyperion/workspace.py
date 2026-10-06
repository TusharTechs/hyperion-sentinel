"""Workspace access (the IDE backend) and path safety.

Reads go straight to the IDE backend REST API. Writes are NOT done here: the IDE
performs them itself when it receives an `action` event over SSE (see actions.py).
"""

from __future__ import annotations

import asyncio
import posixpath
import re
from dataclasses import dataclass, field

import httpx

from . import config


class PathError(ValueError):
    """The requested path is not an acceptable workspace path."""


_BAD_CHARS = re.compile(r"[\x00-\x1f\\:*?\"<>|]")


def safe_path(raw: str) -> str:
    """Normalise an untrusted path to a workspace-relative POSIX path or raise PathError."""
    if not isinstance(raw, str):
        raise PathError("path must be a string")
    p = raw.strip().strip("'\"`").replace("\\", "/")
    if not p:
        raise PathError("empty path")
    if p.startswith("/") or re.match(r"^[A-Za-z]:", p) or p.startswith("~"):
        raise PathError("absolute paths are not allowed")
    if _BAD_CHARS.search(p) or "%" in p:
        raise PathError("path contains invalid characters")
    parts = p.split("/")
    if any(seg == ".." for seg in parts):
        raise PathError("path traversal ('..') is not allowed")
    norm = posixpath.normpath(p)
    if norm in (".", "") or norm.startswith("../"):
        raise PathError("invalid path")
    if len(norm) > 200 or any(len(s) > 100 for s in norm.split("/")):
        raise PathError("path too long")
    if any(s.startswith(".") and s not in (".env", ".env.example", ".dockerignore", ".gitignore", ".env.sample")
           and not s.startswith(".env.") for s in norm.split("/")):
        raise PathError("hidden files and folders are not allowed (except .env*, .dockerignore, .gitignore)")
    return norm


@dataclass
class Snapshot:
    """A read-only copy of the workspace taken at one moment."""

    files: dict[str, str] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)  # too large / unreadable
    error: str | None = None

    def copy(self) -> "Snapshot":
        return Snapshot(dict(self.files), list(self.skipped), self.error)


class WorkspaceError(Exception):
    pass


class IDEWorkspace:
    """Reads the workspace through the IDE backend."""

    def __init__(self, base_url: str | None = None, client: httpx.AsyncClient | None = None):
        self.base_url = (base_url or config.IDE_BACKEND_URL).rstrip("/")
        self._client = client

    def _c(self) -> httpx.AsyncClient:
        return self._client or httpx.AsyncClient(timeout=10)

    async def _get(self, path: str, params: dict):
        client = self._c()
        try:
            return await client.get(f"{self.base_url}{path}", params=params)
        except httpx.HTTPError as exc:
            raise WorkspaceError(f"cannot reach the IDE backend at {self.base_url} ({exc})") from exc
        finally:
            if self._client is None:
                await client.aclose()

    async def _list(self, folder: str, out: list[str], depth: int = 0):
        if depth > 8 or len(out) >= config.MAX_WORKSPACE_FILES:
            return
        r = await self._get("/files", {"path": folder})
        if r.status_code != 200:
            raise WorkspaceError(f"IDE backend returned HTTP {r.status_code} listing '{folder or '/'}'")
        items = r.json()
        dirs = []
        for it in items:
            if it.get("type") == "folder":
                dirs.append(it["path"])
            else:
                out.append(it["path"])
        for d in dirs:
            await self._list(d, out, depth + 1)

    async def snapshot(self) -> Snapshot:
        snap = Snapshot()
        paths: list[str] = []
        try:
            await self._list("", paths)
        except WorkspaceError as exc:
            snap.error = str(exc)
            return snap
        sem = asyncio.Semaphore(8)

        async def read(p: str):
            async with sem:
                try:
                    r = await self._get("/file", {"path": p})
                    if r.status_code != 200:
                        snap.skipped.append(f"{p} (HTTP {r.status_code})")
                        return
                    content = r.json().get("content", "")
                    if len(content.encode("utf-8", "ignore")) > config.MAX_FILE_BYTES:
                        snap.skipped.append(f"{p} (larger than {config.MAX_FILE_BYTES // 1000} KB)")
                        return
                    snap.files[p] = content
                except (WorkspaceError, ValueError) as exc:
                    snap.skipped.append(f"{p} ({exc})")

        await asyncio.gather(*(read(p) for p in paths))
        return snap

    async def validate(self, path: str) -> dict | None:
        """The IDE's own profile validator (starter helper). None if unavailable."""
        from helpers import ValidateFileError, validate_file  # starter helper

        try:
            return await validate_file(path)
        except ValidateFileError:
            return None
