"""Precompute document vectors for hybrid retrieval: uv run python scripts/build_embeddings.py   (needs API_KEY in .env)
Writes knowledge/embeddings.json keyed by chunk hash; re-run whenever knowledge/*.md changes (stale vectors are ignored automatically)."""
import json
import pathlib
import sys

import httpx

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from hyperion import config  # noqa: E402
from hyperion.embeddings import DOC_PREFIX, MODEL  # noqa: E402
from hyperion.rag import KnowledgeBase  # noqa: E402

kb = KnowledgeBase()
assert config.API_KEY, "set API_KEY in .env"
items: dict[str, list[float]] = {}
chunks = kb.chunks
for i in range(0, len(chunks), 16):
    batch = chunks[i:i + 16]
    r = httpx.post(f"{config.LLM_BASE_URL.rstrip('/')}/embeddings", headers={"Authorization": f"Bearer {config.API_KEY}"},
                   json={"model": MODEL, "input": [DOC_PREFIX + (c.title.split(" > ", 1)[-1] + ". " if " > " in c.title else "") + c.text[:2000] for c in batch]}, timeout=120)
    r.raise_for_status()
    for c, d in zip(batch, r.json()["data"]):
        items[c.key] = [round(x, 5) for x in d["embedding"]]
    print(f"{min(i + 16, len(chunks))}/{len(chunks)}", flush=True)
out = pathlib.Path(__file__).resolve().parent.parent / "knowledge" / "embeddings.json"
out.write_text(json.dumps({"model": MODEL, "dim": len(next(iter(items.values()))), "items": items}, separators=(",", ":")))
print("wrote", out, f"{out.stat().st_size / 1e6:.2f} MB")
