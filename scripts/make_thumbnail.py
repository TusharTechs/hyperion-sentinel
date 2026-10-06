"""YouTube thumbnail (1280x720) from a real frame of the live demo. Render: Chrome headless --screenshot."""
import base64
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
img = base64.b64encode((ROOT / "video" / "thumb_frame.jpg").read_bytes()).decode()
MARK = (ROOT / "assets" / "logo.svg").read_text()
inner = MARK.split(">", 1)[1].rsplit("</svg>", 1)[0]  # logo body (defs + shapes)

svg = f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 1280 720" width="1280" height="720">
<defs>
<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#070B16"/><stop offset=".55" stop-color="#101A44"/><stop offset="1" stop-color="#2A1B6E"/></linearGradient>
<radialGradient id="halo" cx="50%" cy="50%" r="50%"><stop offset="0" stop-color="#F59E0B" stop-opacity=".35"/><stop offset="1" stop-color="#F59E0B" stop-opacity="0"/></radialGradient>
<linearGradient id="tx" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#5EEAD4"/><stop offset="1" stop-color="#93C5FD"/></linearGradient>
<clipPath id="card"><rect x="690" y="150" width="520" height="390" rx="22"/></clipPath>
<filter id="sh" x="-20%" y="-20%" width="140%" height="150%"><feDropShadow dx="0" dy="14" stdDeviation="18" flood-color="#000" flood-opacity=".6"/></filter>
</defs>
<style>text{{font-family:'Helvetica Neue','Inter','Arial Black',Arial,sans-serif}}</style>
<rect width="1280" height="720" fill="url(#bg)"/>
<circle cx="260" cy="250" r="330" fill="url(#halo)"/>
<g transform="translate(40 40) scale(.9)">{inner}</g>
<text x="165" y="96" font-size="34" font-weight="800" fill="#E2E8F0" letter-spacing="1">HYPERION SENTINEL</text>
<text x="44" y="330" font-size="190" font-weight="900" fill="#F87171" letter-spacing="-6">35</text>
<path d="M350 270 H420 M398 238 L430 270 L398 302" stroke="#5EEAD4" stroke-width="16" fill="none" stroke-linecap="round" stroke-linejoin="round"/>
<text x="488" y="330" font-size="190" font-weight="900" fill="url(#tx)" letter-spacing="-6">65</text>
<text x="48" y="430" font-size="62" font-weight="900" fill="#FFFFFF">Edge-ready in</text>
<text x="48" y="505" font-size="62" font-weight="900" fill="#FDE68A">ONE chat.</text>
<text x="48" y="570" font-size="32" font-weight="600" fill="#C7D2FE">An AI agent that audits, fixes &amp; verifies</text>
<text x="48" y="610" font-size="32" font-weight="600" fill="#C7D2FE">your HYPER-AI IDE workspace</text>
<g filter="url(#sh)"><rect x="690" y="150" width="520" height="390" rx="22" fill="#0A1124" stroke="#5EEAD4" stroke-opacity=".7" stroke-width="3"/>
<image href="data:image/jpeg;base64,{img}" x="690" y="150" width="520" height="390" preserveAspectRatio="xMidYMid slice" clip-path="url(#card)"/></g>
<rect x="716" y="500" width="150" height="40" rx="20" fill="#F87171"/><circle cx="740" cy="520" r="7" fill="#fff"/><text x="756" y="528" font-size="22" font-weight="800" fill="#fff">LIVE</text>
<rect x="690" y="580" width="520" height="70" rx="16" fill="#0E1A3A" stroke="#93C5FD" stroke-opacity=".5" stroke-width="2"/>
<text x="950" y="626" text-anchor="middle" font-size="28" font-weight="800" fill="#BFDBFE">real HYPER-AI IDE  ·  real Llama 3.1</text>
</svg>'''
(ROOT / "assets" / "thumbnail.svg").write_text(svg)
print("thumbnail.svg written")
