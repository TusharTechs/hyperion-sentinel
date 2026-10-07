"""Deterministic facts extracted from the official HyperAI IDE tutorial tables (no LLM involved).

Currently: the required (check-marked) fields of native and device application profiles."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

TUTORIAL = Path(__file__).resolve().parent.parent / "knowledge" / "HyperAI_IDE_Tutorial.md"
SOURCE = "HyperAI IDE tutorial > "


@lru_cache(maxsize=1)
def _profiles() -> dict[str, dict]:
    """{'native'|'device': {'top': [...], 'sections': [(heading, [required fields])]}} parsed from the tutorial markdown."""
    try:
        text = TUTORIAL.read_text(encoding="utf-8")
    except OSError:
        return {}
    out: dict[str, dict] = {}
    kind = None
    heading = ""
    in_code = False
    header_cols: list[str] = []
    for ln in text.splitlines():
        if ln.strip().startswith("```"):
            in_code = not in_code
        if in_code:
            continue
        if ln.startswith("# "):
            t = ln[2:].strip()
            kind = "native" if t.startswith("Defining Native") else "device" if t.startswith("Defining Device") else None
            if kind:
                out[kind] = {"top": [], "sections": []}
            heading = ""
            continue
        if kind is None:
            continue
        m = re.match(r"^#{2,4}\s+(.*)$", ln)
        if m:
            heading = re.sub(r"[`*]", "", m.group(1)).split(" — ")[0].strip()
            header_cols = []
            continue
        if ln.lstrip().startswith("|"):
            cells = [c.strip() for c in ln.strip().strip("|").split("|")]
            if cells and cells[0].lower() == "field":
                header_cols = [c.lower() for c in cells]
                continue
            if set("".join(cells)) <= set("-: "):
                continue
            if "required" in header_cols and len(cells) == len(header_cols):
                if "✅" in cells[header_cols.index("required")]:
                    field = cells[0].strip("`")
                    if heading in ("Profile Structure", "Manifest Structure"):
                        out[kind]["top"].append(field)
                    else:
                        secs = out[kind]["sections"]
                        if not secs or secs[-1][0] != heading:
                            secs.append((heading, []))
                        secs[-1][1].append(field)
    return out


def required_fields(kind: str) -> str | None:
    p = _profiles().get(kind)
    if not p or not p["sections"]:
        return None
    label = "native" if kind == "native" else "device"
    lines = [f"Required fields of a {label} application profile (from the official DSL specification):", ""]
    if p["top"]:
        lines.append("Top level: " + ", ".join(p["top"]) + ".")
    for heading, fields in p["sections"]:
        lines.append(f"  - {heading}: " + ", ".join(fields))
    if kind == "device":
        lines.append("  (Exactly one workload block is needed: the one matching spec.workload.kind - AndroidApk, DockerImage or esp32Binary.)")
    lines += ["", "Fields not marked required in the tables are optional; `status` is set by the platform. "
                  "The IDE's Validation button checks a profile against these rules.",
              "", "Source: " + SOURCE + ("Defining Native Applications" if kind == "native" else "Defining Device Node Applications")]
    return "\n".join(lines)
