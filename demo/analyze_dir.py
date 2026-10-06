"""Run the Edge Readiness analyzer over a local directory (no IDE needed): python demo/analyze_dir.py demo/hero"""
import asyncio
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from hyperion.analyzer.engine import analyze_workspace  # noqa: E402
from hyperion.workspace import Snapshot  # noqa: E402

root = pathlib.Path(sys.argv[1])
snap = Snapshot({str(p.relative_to(root)): p.read_text(errors="ignore") for p in root.rglob("*") if p.is_file()})
r = asyncio.run(analyze_workspace(snap))
print("SCORE", r.score, r.counts())
for f in r.findings:
    print(f.severity.ljust(8), f.automation_safety.ljust(16), f.rule.ljust(18), f.file, f.line, "|", f.evidence)
for g in r.good:
    print("GOOD", g.finding)
