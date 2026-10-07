"""Optional dense retrieval support via the hosted OpenAI-compatible /embeddings endpoint (nomic-embed-text).

Document vectors are precomputed (knowledge/embeddings.json) so only the *query* is embedded at runtime, with a short timeout.
Any failure returns None and retrieval silently falls back to BM25.
"""

from __future__ import annotations

import json
import os

import httpx

from . import config

MODEL = os.environ.get("EMBED_MODEL", "nomic-embed-text")
QUERY_PREFIX = "search_query: "
DOC_PREFIX = "search_document: "
TIMEOUT = float(os.environ.get("EMBED_TIMEOUT", "2.5"))


async def embed_query(text: str) -> list[float] | None:
    if not config.API_KEY or os.environ.get("EMBED_DISABLED") == "1":
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.post(f"{config.LLM_BASE_URL.rstrip('/')}/embeddings",
                                  headers={"Authorization": f"Bearer {config.API_KEY}"},
                                  json={"model": MODEL, "input": [QUERY_PREFIX + text[:1000]]})
        r.raise_for_status()
        return r.json()["data"][0]["embedding"]
    except Exception:
        return None


def load_vectors(path) -> dict[str, list[float]]:
    try:
        data = json.loads(open(path, encoding="utf-8").read())
        return data["items"] if data.get("model") == MODEL else {}
    except Exception:
        return {}
