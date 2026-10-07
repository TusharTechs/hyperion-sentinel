"""Turn the official HyperAI IDE tutorial (https://ide-tutorial.hyperai.di.uoa.gr/llms-full.txt) into knowledge/HyperAI_IDE_Tutorial.md.
Usage: curl -sL https://ide-tutorial.hyperai.di.uoa.gr/llms-full.txt -o knowledge/_incoming/llms-full.txt && python3 scripts/build_tutorial_knowledge.py
Strips link URLs and horizontal rules; keeps headings, tables and code so retrieval can cite sections."""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
src = (ROOT / "knowledge" / "_incoming" / "llms-full.txt").read_text(encoding="utf-8")
src = re.sub(r"\[([^\]]+)\]\((?:https?://[^)]*|#[^)]*)\)", r"\1", src)          # [text](url) -> text
src = re.sub(r"^_{5,}\s*$", "", src, flags=re.M)                                # horizontal rules
src = re.sub(r"\n{3,}", "\n\n", src).strip() + "\n"
(ROOT / "knowledge" / "HyperAI_IDE_Tutorial.md").write_text(src, encoding="utf-8")
print("wrote knowledge/HyperAI_IDE_Tutorial.md", len(src), "chars")
