"""Convert the official HYPER-AI .docx deliverables in knowledge/ to clean .md files for RAG.

Usage: uv run python scripts/build_knowledge.py
Strips page footers/figure captions and re-joins hard-wrapped lines into paragraphs.
"""
import glob
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
FOOTER = re.compile(r"^(HYPER-AI \| GA: \d+|\d{1,3}|Figure \d+\s*:.*)$")


def paragraphs(path: str) -> list[str]:
    root = ET.fromstring(zipfile.ZipFile(path).read("word/document.xml"))
    return [t for p in root.iter(W + "p") if (t := "".join(x.text or "" for x in p.iter(W + "t")).strip())]


def merge(lines: list[str]) -> list[str]:
    out: list[str] = []
    for ln in lines:
        if FOOTER.match(ln):
            continue
        starts_new = bool(re.match(r"^([•\-•]|\d+\.|[A-Z][A-Za-z\- ]{2,40}:)\s", ln)) or ln.isupper()
        if out and not starts_new and not re.search(r"[.:?!]$", out[-1]) or (out and not starts_new and ln[:1].islower()):
            out[-1] += " " + ln
        else:
            out.append(ln)
    return out


if __name__ == "__main__":
    for f in sorted(glob.glob("knowledge/*.docx")):
        text = "\n\n".join(merge(paragraphs(f))) + "\n"
        Path(f[:-5] + ".md").write_text(text)
        print(f, "->", len(text), "chars")
