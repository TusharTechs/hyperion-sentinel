"""Lightweight RAG: heading/paragraph-aware chunking + BM25 over the bundled HYPER-AI docs."""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .embeddings import load_vectors

KNOWLEDGE_DIR = Path(__file__).resolve().parent.parent / "knowledge"
EMBEDDINGS_FILE = KNOWLEDGE_DIR / "embeddings.json"
STOP = set("a an the of to in on for and or is are was were be been it its this that with as by at from what how which who does do can i you we me my your about tell please explain".split())
TITLES = {
    "D3.3_2.1_Methodology": "HYPER-AI D3.3 - Design methodology",
    "D3.3_Executive_Summary": "HYPER-AI D3.3 - Executive summary (architecture)",
    "D4.2_2.1_Open_Connectors_Overview": "HYPER-AI D4.2 - Open Connectors overview",
    "D4.2_3.1_High_Level_Architecture": "HYPER-AI D4.2 - Open Connectors high-level architecture",
    "D4.2_Executive_Summary": "HYPER-AI D4.2 - Executive summary (Open Connectors)",
    "D4.3_Executive_Summary": "HYPER-AI D4.3 - Executive summary (application profiles)",
    "HyperAI_IDE_Tutorial": "HyperAI IDE tutorial",
    "HyperAI_IDE_Notes": "HyperAI IDE and challenge overview",
}


@dataclass
class Chunk:
    source: str
    title: str
    text: str

    @property
    def key(self) -> str:
        """Stable id used to match precomputed embeddings to this exact chunk text."""
        return hashlib.sha1((self.title + "\n" + self.text).encode("utf-8")).hexdigest()


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


TABLE_MAX = 1700  # tables (e.g. the action list) stay whole when reasonably small
HEADING = re.compile(r"^(#{1,4})\s+(.+?)\s*$")


def _blocks(lines: list[str]) -> list[str]:
    """Split a section body into blocks: paragraphs, whole fenced code blocks, whole tables."""
    blocks, cur, in_code = [], [], False
    for ln in lines:
        if ln.strip().startswith("```"):
            if in_code:
                cur.append(ln); blocks.append("\n".join(cur)); cur, in_code = [], False
            else:
                if cur:
                    blocks.append("\n".join(cur)); cur = []
                cur, in_code = [ln], True
            continue
        if in_code:
            cur.append(ln); continue
        if not ln.strip():
            if cur:
                blocks.append("\n".join(cur)); cur = []
        elif cur and cur[0].lstrip().startswith("|") != ln.lstrip().startswith("|"):
            blocks.append("\n".join(cur)); cur = [ln]  # a table starts or ends
        else:
            cur.append(ln)
    if cur:
        blocks.append("\n".join(cur))
    return [b for b in blocks if b.strip()]


def _split_big(block: str, max_chars: int) -> list[str]:
    """Keep oversized tables readable (header repeated) and oversized code/text split on line boundaries."""
    is_table = block.lstrip().startswith("|")
    if len(block) <= (TABLE_MAX if is_table else max_chars):
        return [block]
    lines = block.split("\n")
    head = lines[:2] if lines[0].lstrip().startswith("|") and len(lines) > 2 else []
    out, cur = [], list(head)
    for ln in lines[len(head):]:
        if sum(len(x) + 1 for x in cur) + len(ln) > max_chars and len(cur) > len(head):
            out.append("\n".join(cur)); cur = list(head)
        cur.append(ln)
    if len(cur) > len(head):
        out.append("\n".join(cur))
    return out


def sections(text: str) -> list[tuple[str, list[str]]]:
    """Markdown -> [(heading path, body lines)]; the path nests by heading level, same-level headings replace each other."""
    stack: list[tuple[int, str]] = []
    out: list[tuple[str, list[str]]] = []
    cur: list[str] = []
    path = ""
    in_code = False
    for ln in text.splitlines():
        if ln.strip().startswith("```"):
            in_code = not in_code
        m = None if in_code else HEADING.match(ln)
        if m:
            out.append((path, cur)); cur = []
            level, title = len(m.group(1)), m.group(2).strip().strip("*")
            stack = [x for x in stack if x[0] < level] + [(level, title)]
            titles = []
            for _, t in stack:
                if not titles or titles[-1] != t:
                    titles.append(t)
            path = " > ".join(titles)
        else:
            cur.append(ln)
    out.append((path, cur))
    return [(p, body) for p, body in out if any(x.strip() for x in body)]


def chunk_text(text: str, max_chars: int = 1000) -> list[tuple[str, str]]:
    """Heading-aware chunking: [(section path, chunk text)]. Documents without headings fall back to paragraph windows."""
    chunks: list[tuple[str, str]] = []
    # merge small sibling sections (e.g. the numbered steps of a procedure) so a how-to stays in one chunk
    merged: list[list] = []  # [parent path, body lines, size]
    for path, body in sections(text):
        parent = path.rsplit(" > ", 1)[0] if " > " in path else path
        size = sum(len(x) + 1 for x in body)
        label = path.rsplit(" > ", 1)[-1] if path else ""
        if merged and merged[-1][0] == parent and merged[-1][2] + size + len(label) <= max_chars and size < max_chars // 2 and path != parent \
                or merged and merged[-1][0] == parent and path == parent and False:
            merged[-1][1] += ["", f"{label}:"] + body
            merged[-1][2] += size + len(label) + 2
        else:
            merged.append([parent if path else "", list(body), size])
    for path, body in ((m[0], m[1]) for m in merged):
        cur: list[str] = []
        size = 0
        for blk in (piece for b in _blocks(body) for piece in _split_big(b, max_chars)):
            if cur and size + len(blk) > max_chars:
                chunks.append((path, "\n\n".join(cur)))
                cur = cur[-1:] if len(cur[-1]) < max_chars // 3 else []   # one-block overlap, only when the block is small
                size = sum(len(x) for x in cur)
            cur.append(blk); size += len(blk)
        if cur:
            chunks.append((path, "\n\n".join(cur)))
    return chunks


class KnowledgeBase:
    def __init__(self, directory: Path | None = None):
        self.chunks: list[Chunk] = []
        d = Path(directory or KNOWLEDGE_DIR)
        for f in sorted(d.glob("*.md")):
            title = TITLES.get(f.stem, f.stem.replace("_", " "))
            for path, c in chunk_text(f.read_text(encoding="utf-8")):
                self.chunks.append(Chunk(f.stem, f"{title} > {path}" if path else title, c))
        self._tf = [Counter(tokenize(c.title.split(' > ', 1)[-1] + ' ' + c.text) if ' > ' in c.title else tokenize(c.text)) for c in self.chunks]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = (sum(self._len) / len(self._len)) if self._len else 1
        df: Counter = Counter()
        for tf in self._tf:
            df.update(tf.keys())
        n = len(self.chunks)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        vecs = load_vectors(Path(directory or KNOWLEDGE_DIR) / "embeddings.json")
        self._vec = [vecs.get(c.key) for c in self.chunks]
        self.dense_ready = bool(self.chunks) and all(v is not None for v in self._vec)

    def _bm25(self, query: str) -> list[tuple[float, int]]:
        q = tokenize(query)
        scored = []
        for i, tf in enumerate(self._tf):
            sc = 0.0
            for t in set(q):
                if t in tf:
                    f = tf[t]
                    sc += self._idf[t] * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * self._len[i] / self._avg))
            if sc > 0:
                scored.append((sc, i))
        scored.sort(key=lambda x: -x[0])
        return scored

    def _dense(self, qv: list[float]) -> list[tuple[float, int]]:
        qn = math.sqrt(sum(x * x for x in qv)) or 1.0
        out = []
        for i, v in enumerate(self._vec):
            dn = math.sqrt(sum(x * x for x in v)) or 1.0
            out.append((sum(a * b for a, b in zip(qv, v)) / (qn * dn), i))
        out.sort(key=lambda x: -x[0])
        return out

    def search(self, query: str, k: int = 4, min_score: float = 0.05, query_vec: list[float] | None = None) -> list[tuple[float, Chunk]]:
        """BM25, fused with dense similarity (reciprocal rank fusion) when a query vector and doc vectors are available."""
        bm = self._bm25(query)
        if query_vec is not None and self.dense_ready and len(query_vec) == len(self._vec[0]):
            dn = self._dense(query_vec)[:12]
            fused: dict[int, float] = {}
            for rank, (_, i) in enumerate(bm[:12]):
                fused[i] = fused.get(i, 0.0) + 1.0 / (60 + rank)
            for rank, (_, i) in enumerate(dn):
                fused[i] = fused.get(i, 0.0) + 1.0 / (60 + rank)
            order = sorted(fused.items(), key=lambda x: -x[1])[:k]
            bm_score = dict((i, s_) for s_, i in bm)
            # report the BM25 score when there is one (callers use it as a rough relevance signal), else a small positive value
            return [(max(bm_score.get(i, 0.0), 0.06), self.chunks[i]) for i, _ in order]
        scored = [(s_, self.chunks[i]) for s_, i in bm if s_ >= min_score]
        if scored:  # drop weak tail relative to the best hit
            scored = [x for x in scored if x[0] >= 0.35 * scored[0][0]]
        return scored[:k]
