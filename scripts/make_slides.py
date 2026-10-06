"""Generate 16:9 presentation slides (SVG) from the project assets. PNGs: qlmanage -t -s 1600 -o . *.svg (macOS)."""
import re
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "assets" / "slides"
OUT.mkdir(parents=True, exist_ok=True)
ROOT = OUT.parent

BG = '''<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#070B16"/><stop offset=".6" stop-color="#0E1736"/><stop offset="1" stop-color="#1B1650"/></linearGradient>
<linearGradient id="tx" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#5EEAD4"/><stop offset=".55" stop-color="#93C5FD"/><stop offset="1" stop-color="#C4B5FD"/></linearGradient>
<linearGradient id="sh" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1B2A4E"/><stop offset="1" stop-color="#0A1020"/></linearGradient>
<linearGradient id="rim" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#5EEAD4"/><stop offset="1" stop-color="#6366F1"/></linearGradient>
<radialGradient id="sun" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#FDE68A"/><stop offset="1" stop-color="#F59E0B"/></radialGradient>
<radialGradient id="halo" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#F59E0B" stop-opacity=".30"/><stop offset="1" stop-color="#F59E0B" stop-opacity="0"/></radialGradient>
<pattern id="grid" width="48" height="48" patternUnits="userSpaceOnUse"><path d="M48 0H0V48" fill="none" stroke="#5EEAD4" stroke-opacity=".06"/></pattern>
<filter id="glow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2.4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>
<style>text{font-family:'Helvetica Neue','Inter','Segoe UI',Arial,sans-serif}</style>
<rect width="1600" height="900" fill="url(#bg)"/><rect width="1600" height="900" fill="url(#grid)"/>'''

MARK = '''<g transform="translate({x} {y}) scale({s})"><path d="M64 7 L113 25 V62 C113 91 92 111 64 121 C36 111 15 91 15 62 V25 Z" fill="url(#sh)" stroke="url(#rim)" stroke-width="3.5" stroke-linejoin="round"/>
<g filter="url(#glow)" stroke="#FBBF24" stroke-width="3.2" stroke-linecap="round"><line x1="64" y1="21" x2="64" y2="28"/><line x1="43" y1="30" x2="48" y2="35"/><line x1="85" y1="30" x2="80" y2="35"/><line x1="34" y1="49" x2="41" y2="49"/><line x1="94" y1="49" x2="87" y2="49"/><line x1="43" y1="68" x2="48" y2="63"/><line x1="85" y1="68" x2="80" y2="63"/></g>
<circle cx="64" cy="49" r="13.5" fill="url(#sun)" filter="url(#glow)"/><path d="M30 78 H98" stroke="#5EEAD4" stroke-opacity=".35" stroke-width="2" stroke-linecap="round" stroke-dasharray="2 6"/>
<path d="M44 90 L57 103 L84 76" fill="none" stroke="#5EEAD4" stroke-width="8" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)"/></g>'''


def wrap(body: str) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900" width="1600" height="900">{BG}{body}</svg>'


def pill(x, label, color, light):
    return (f'<rect x="{x}" y="620" width="190" height="56" rx="28" fill="{color}" fill-opacity=".12" stroke="{color}" stroke-opacity=".5"/>'
            f'<text x="{x + 95}" y="657" text-anchor="middle" fill="{light}">{label}</text>')


cover = ('<circle cx="330" cy="450" r="330" fill="url(#halo)"/><g fill="none" stroke="#5EEAD4" stroke-opacity=".10"><circle cx="330" cy="450" r="200"/><circle cx="330" cy="450" r="270"/><circle cx="330" cy="450" r="350"/></g>'
         + MARK.format(x=150, y=270, s=2.8)
         + '<text x="610" y="400" font-size="108" font-weight="800" fill="url(#tx)" letter-spacing="-2">Hyperion</text>'
           '<text x="610" y="505" font-size="108" font-weight="800" fill="url(#tx)" letter-spacing="-2">Sentinel</text>'
           '<text x="614" y="575" font-size="34" fill="#C7D2FE">The edge-readiness engineer inside the HYPER-AI IDE</text>'
           '<g font-size="26" font-weight="700">' + pill(614, "Inspect", "#5EEAD4", "#99F6E4") + pill(824, "Explain", "#93C5FD", "#BFDBFE")
         + pill(1034, "Fix safely", "#C4B5FD", "#DDD6FE") + pill(1244, "Verify", "#FCD34D", "#FDE68A") + '</g>'
           '<text x="614" y="780" font-size="24" fill="#94A3B8">Veles Hack 2026 - Challenge 1 (HYPER-AI)   |   github.com/TusharTechs/hyperion-sentinel</text>')
(OUT / "1-cover.svg").write_text(wrap(cover))

arch = (ROOT / "architecture.svg").read_text()
inner = re.sub(r"^<svg[^>]*>", "", arch).rsplit("</svg>", 1)[0]
(OUT / "2-architecture.svg").write_text(
    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1600 900" width="1600" height="900"><rect width="1600" height="900" fill="#070B16"/>'
    f'<svg x="125" y="0" width="1350" height="900" viewBox="0 0 1280 850" preserveAspectRatio="xMidYMid meet">{inner}</svg></svg>')

rows = [("1", "Working agent + IDE actions", "create / edit / delete files, opened in the editor", "#5EEAD4"),
        ("2", "Guardrails", "scope + prompt-injection rules; fails closed; never touches files", "#F87171"),
        ("3", "RAG", "BM25 over the official HYPER-AI docs; cited; admits gaps", "#93C5FD"),
        ("4", "Memory", "per user_id: findings, plan, facts, last file - fix the second issue", "#C4B5FD"),
        ("5", "Human-in-the-loop", "every delete, overwrite and plan waits for an explicit yes", "#FCD34D")]
body = ('<text x="100" y="120" font-size="54" font-weight="800" fill="url(#tx)">Every challenge criterion - verified</text>'
        '<text x="100" y="168" font-size="26" fill="#94A3B8">203 automated tests, a real IDE run, and a live Llama 3.1 run</text>')
y = 230
for n, t, d, c in rows:
    body += (f'<rect x="100" y="{y}" width="1400" height="96" rx="18" fill="#0E1A3A" stroke="{c}" stroke-opacity=".55" stroke-width="2"/>'
             f'<circle cx="160" cy="{y + 48}" r="28" fill="{c}" fill-opacity=".15" stroke="{c}"/>'
             f'<text x="160" y="{y + 58}" text-anchor="middle" font-size="30" font-weight="800" fill="{c}">{n}</text>'
             f'<text x="220" y="{y + 44}" font-size="32" font-weight="700" fill="#E2E8F0">{t}</text>'
             f'<text x="220" y="{y + 78}" font-size="23" fill="#94A3B8">{d}</text>')
    y += 112
body += (f'<rect x="100" y="{y}" width="1400" height="66" rx="18" fill="#F59E0B" fill-opacity=".10" stroke="#F59E0B" stroke-opacity=".6" stroke-width="2"/>'
         f'<text x="140" y="{y + 43}" font-size="27" font-weight="700" fill="#FDE68A">Differentiator: deterministic Edge Readiness analyzer + safe auto-fix, re-verified via the IDE</text>')
(OUT / "3-criteria.svg").write_text(wrap(body))

ba = ('<text x="100" y="120" font-size="54" font-weight="800" fill="url(#tx)">From "latest" to edge-ready in four messages</text>'
      '<text x="100" y="168" font-size="26" fill="#94A3B8">Hero demo: a deliberately imperfect app in the HYPER-AI IDE</text>'
      '<rect x="100" y="215" width="740" height="585" rx="22" fill="#0E1A3A" stroke="#F87171" stroke-opacity=".5" stroke-width="2"/>'
      '<text x="140" y="268" font-size="22" font-weight="700" letter-spacing="3" fill="#94A3B8">BEFORE</text><text x="140" y="400" font-size="150" font-weight="800" fill="#F87171">35</text><text x="440" y="400" font-size="44" fill="#64748B">/100</text>'
      '<g font-size="26" fill="#CBD5E1"><text x="140" y="470">HIGH    no resource requests / limits</text><text x="140" y="512">HIGH    no readiness probe</text><text x="140" y="554">MEDIUM  image uses :latest</text><text x="140" y="596">MEDIUM  runs as root, no HEALTHCHECK</text><text x="140" y="638">LOW     no .dockerignore, replicas: 5</text><text x="140" y="680">HIGH    hardcoded secret (manual)</text></g>'
      '<path d="M870 507 H915 M900 485 L920 507 L900 529" stroke="#5EEAD4" stroke-width="7" fill="none" stroke-linecap="round" stroke-linejoin="round"/>'
      '<rect x="940" y="215" width="560" height="585" rx="22" fill="#0E1A3A" stroke="#5EEAD4" stroke-opacity=".6" stroke-width="2"/>'
      '<text x="980" y="268" font-size="22" font-weight="700" letter-spacing="3" fill="#94A3B8">AFTER</text><text x="980" y="400" font-size="150" font-weight="800" fill="#5EEAD4">65</text><text x="1260" y="400" font-size="44" fill="#64748B">/100</text>'
      '<text x="980" y="462" font-size="30" font-weight="700" fill="#99F6E4">+30 improvement</text>'
      '<g font-size="25" fill="#CBD5E1"><text x="980" y="520">12 findings resolved</text><text x="980" y="562">files rewritten in the IDE</text><text x="980" y="604">re-read and re-analyzed</text><text x="980" y="646" fill="#FCD34D">5 manual actions remain</text><text x="980" y="688" fill="#94A3B8">(secret, deps, tags ...)</text></g>'
      '<text x="100" y="850" font-size="22" fill="#64748B">Score = Sentinel\'s own deterministic heuristic - not an official HYPER-AI metric. Numbers from a real run.</text>')
(OUT / "4-before-after.svg").write_text(wrap(ba))
print("slides written")

# ---- video scenes (problem / impact / close) ----
problem = ('<text x="100" y="120" font-size="58" font-weight="800" fill="url(#tx)">Edge deployments fail on the basics</text>'
           '<text x="100" y="170" font-size="28" fill="#94A3B8">From IoT devices to the cloud, constrained nodes punish sloppy configuration</text>')
items = [("image: app:latest", "unpinned images change under you", "#F87171"), ("no resources.limits", "one container can starve the node", "#FB923C"),
         ("no readiness probe", "traffic hits pods that are not ready", "#FBBF24"), ("runs as root", "a breach owns the host", "#F472B6"),
         ("password in config", "secrets leak through git and images", "#C4B5FD")]
y = 235
for t, d, c in items:
    problem += (f'<rect x="100" y="{y}" width="1400" height="100" rx="18" fill="#0E1A3A" stroke="{c}" stroke-opacity=".6" stroke-width="2"/>'
                f'<text x="150" y="{y + 62}" font-size="38" font-weight="700" fill="{c}" style="font-family:Menlo,Consolas,monospace">{t}</text>'
                f'<text x="760" y="{y + 60}" font-size="30" fill="#CBD5E1">{d}</text>')
    y += 120
problem += '<text x="100" y="870" font-size="26" fill="#94A3B8">...and developers lose hours digging through YAML to find them.</text>'
(OUT / "5-problem.svg").write_text(wrap(problem))

impact = ('<text x="100" y="120" font-size="58" font-weight="800" fill="url(#tx)">One conversation instead of a manual audit</text>'
          '<text x="100" y="170" font-size="28" fill="#94A3B8">Hyperion Sentinel, inside the HYPER-AI IDE</text>')
cards = [("35 → 65", "edge readiness, verified by re-reading the IDE", "#5EEAD4"), ("7", "analysis areas: Docker, K8s, Compose, HYPER-AI profiles, deps, secrets, completeness", "#93C5FD"),
         ("0", "changes without your explicit yes - every delete, overwrite and plan asks first", "#FCD34D"), ("203", "automated tests, a real IDE run, and a live Llama 3.1 run", "#C4B5FD")]
x = 100
for big, small, c in cards:
    impact += (f'<rect x="{x}" y="260" width="325" height="400" rx="22" fill="#0E1A3A" stroke="{c}" stroke-opacity=".6" stroke-width="2"/>'
               f'<text x="{x + 162}" y="400" text-anchor="middle" font-size="{78 if len(big) < 5 else 62}" font-weight="800" fill="{c}">{big}</text>')
    words, line, ly = small.split(), "", 470
    for w in words:
        if len(line) + len(w) > 22:
            impact += f'<text x="{x + 162}" y="{ly}" text-anchor="middle" font-size="24" fill="#CBD5E1">{line.strip()}</text>'; ly += 34; line = ""
        line += w + " "
    impact += f'<text x="{x + 162}" y="{ly}" text-anchor="middle" font-size="24" fill="#CBD5E1">{line.strip()}</text>'
    x += 358
impact += '<text x="100" y="780" font-size="30" font-weight="700" fill="#FDE68A">Deterministic tools produce the facts. The LLM only converses.</text>'
(OUT / "6-impact.svg").write_text(wrap(impact))

close = ('<circle cx="800" cy="330" r="300" fill="url(#halo)"/>' + MARK.format(x=670, y=170, s=2.0) +
         '<text x="800" y="520" text-anchor="middle" font-size="84" font-weight="800" fill="url(#tx)">Hyperion Sentinel</text>'
         '<text x="800" y="580" text-anchor="middle" font-size="32" fill="#C7D2FE">Inspect  -  Explain  -  Fix safely  -  Verify</text>'
         '<text x="800" y="680" text-anchor="middle" font-size="30" fill="#99F6E4">github.com/TusharTechs/hyperion-sentinel</text>'
         '<text x="800" y="728" text-anchor="middle" font-size="30" fill="#BFDBFE">docker run tushartechs/hyperion:latest</text>'
         '<text x="800" y="810" text-anchor="middle" font-size="22" fill="#64748B">Veles Hack 2026 - Challenge 1 (HYPER-AI) - built on the official hyperion-starter</text>')
(OUT / "7-close.svg").write_text(wrap(close))
print("video scenes written")
