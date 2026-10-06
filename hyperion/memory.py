"""Bounded per-user session memory, keyed by the IDE-provided user_id."""

from __future__ import annotations

import time
from collections import OrderedDict, deque
from dataclasses import dataclass, field

from . import config
from .models import Finding, Report

SESSION_TTL = 6 * 3600
MAX_MSG_CHARS = 1500
MAX_FINDINGS_KEPT = 80


@dataclass
class Session:
    user_id: str
    history: deque = field(default_factory=lambda: deque(maxlen=config.MAX_HISTORY_TURNS * 2))
    report: Report | None = None
    findings: list[Finding] = field(default_factory=list)  # numbering shown to the user (1-based)
    plan: dict | None = None  # {"safe": [...], "confirm": [...], "manual": [...]}
    pending: dict | None = None  # awaiting yes/no: {"type": "delete"|"apply"|"overwrite", ...}
    changes_log: list[dict] = field(default_factory=list)  # newest last, bounded
    last_files: list[str] = field(default_factory=list)
    facts: dict = field(default_factory=dict)  # things the user told us: name, service, ...
    last_file: str | None = None  # last file Hyperion created/edited (resolves "it", "that file")
    last_image: str | None = None  # last container image the user mentioned (resolves "for it")
    known_files: dict = field(default_factory=dict)  # path -> content of files Hyperion wrote this session
    touched: float = field(default_factory=time.time)

    def remember(self, role: str, text: str):
        self.history.append({"role": role, "content": text[:MAX_MSG_CHARS]})

    def set_report(self, report: Report):
        self.report = report
        self.findings = report.findings[:MAX_FINDINGS_KEPT]
        self.plan = None

    def note_action(self, act: dict):
        """Track what Hyperion did to the workspace so follow-ups and offline operation work."""
        kind, path = act.get("action"), act.get("path")
        if not path:
            return
        if kind in ("create_file", "edit_file"):
            self.known_files[path] = str(act.get("content", ""))[:20000]
            self.last_file = path
            while len(self.known_files) > 30:
                self.known_files.pop(next(iter(self.known_files)))
        elif kind == "delete_file":
            self.known_files.pop(path, None)
            if self.last_file == path:
                self.last_file = None
        elif kind == "delete_folder":
            for k in [k for k in self.known_files if k.startswith(path + "/")]:
                del self.known_files[k]

    def log_change(self, entry: dict):
        self.changes_log.append(entry)
        del self.changes_log[:-5]


class SessionStore:
    def __init__(self, max_sessions: int | None = None):
        self._s: OrderedDict[str, Session] = OrderedDict()
        self.max = max_sessions or config.MAX_SESSIONS

    def get(self, user_id: str) -> Session:
        now = time.time()
        for uid in [u for u, s in self._s.items() if now - s.touched > SESSION_TTL]:
            del self._s[uid]
        sess = self._s.get(user_id)
        if sess is None:
            sess = Session(user_id)
            self._s[user_id] = sess
        sess.touched = now
        self._s.move_to_end(user_id)
        while len(self._s) > self.max:
            self._s.popitem(last=False)
        return sess

    def __len__(self):
        return len(self._s)
