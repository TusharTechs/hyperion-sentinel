"""Lightweight RAG: heading/paragraph-aware chunking + BM25 over the bundled HYPER-AI docs."""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
STOP = set("a an the of to in on for and or is are was were be been it its this that with as by at from what how which who does do can i you we me my your about tell please explain".split())
TITLES = {
    "D3.3_2.1_Methodology": "HYPER-AI D3.3 - Design methodology",
    "D3.3_Executive_Summary": "HYPER-AI D3.3 - Executive summary (architecture)",
    "D4.2_2.1_Open_Connectors_Overview": "HYPER-AI D4.2 - Open Connectors overview",
    "D4.2_3.1_High_Level_Architecture": "HYPER-AI D4.2 - Open Connectors high-level architecture",
    "D4.2_Executive_Summary": "HYPER-AI D4.2 - Executive summary (Open Connectors)",
    "D4.3_Executive_Summary": "HYPER-AI D4.3 - Executive summary (application profiles)",
    "HyperAI_IDE_Notes": "HyperAI IDE notes (challenge description / IDE validator)",
}


@dataclass
class Chunk:
    source: str
    title: str
    text: str


def tokenize(text: str) -> list[str]:
    text = re.sub(r"hyper\s*-?\s*ai", "hyper-ai", text.lower())
    toks = re.findall(r"[a-z0-9][a-z0-9\-\.]*[a-z0-9]|[a-z0-9]", text.lower())
    out = []
    for t in toks:
        if t in STOP:
            continue
        out.append(t)
        if t.endswith("s") and len(t) > 3:
            out.append(t[:-1])
        if "-" in t and t != "hyper-ai":
            out.extend(p for p in t.split("-") if p and p not in STOP)
    return out


def chunk_text(text: str, max_chars: int = 700) -> list[str]:
    """Paragraphs grouped into ~max_chars windows with one-paragraph overlap."""
    paras = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    chunks, cur = [], []
    size = 0
    for p in paras:
        if cur and size + len(p) > max_chars:
            chunks.append("\n\n".join(cur))
            cur = cur[-1:] if len(cur[-1]) < max_chars // 2 else []
            size = sum(len(x) for x in cur)
        cur.append(p)
        size += len(p)
    if cur:
        chunks.append("\n\n".join(cur))
    return chunks


class KnowledgeBase:
    def __init__(self, directory: Path | None = None):
        self.chunks: list[Chunk] = []
        d = Path(directory or KNOWLEDGE_DIR)
        for f in sorted(d.glob("*.md")):
            title = TITLES.get(f.stem, f.stem.replace("_", " "))
            for c in chunk_text(f.read_text(encoding="utf-8")):
                self.chunks.append(Chunk(f.stem, title, c))
        self._tf = [Counter(tokenize(c.text)) for c in self.chunks]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = (sum(self._len) / len(self._len)) if self._len else 1
        df: Counter = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(self.chunks)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def search(self, query: str, k: int = 4, min_score: float = 0.05) -> list[tuple[float, Chunk]]:
        q = tokenize(query)
        scored = []
        for i, tf in enumerate(self._tf):
            s = 0.0
            for t in set(q):
                if t in tf:
                    f = tf[t]
                    s += self._idf[t] * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * self._len[i] / self._avg))
            if s >= min_score:
                scored.append((s, self.chunks[i]))
        scored.sort(key=lambda x: -x[0])
        if scored:  # drop weak tail relative to the best hit
            scored = [x for x in scored if x[0] >= 0.35 * scored[0][0]]
        return scored[:k]
