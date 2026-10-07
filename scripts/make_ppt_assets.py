"""Graphics for the submission deck (light theme matching the Veles Hack template: navy 25346A, orange EF7C14, teal 0097A7).
Run: uv run --with qrcode --with pillow python scripts/make_ppt_assets.py   (then render with headless Chrome, see render())"""
import base64
import io
import pathlib
import subprocess

import qrcode

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "ppt"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
NAVY, ORANGE, TEAL, INK, MUTED, CARD = "#25346A", "#EF7C14", "#0097A7", "#1F2937", "#5B6475", "#F3F6FB"

BASE = f"""<style>*{{box-sizing:border-box}}html,body{{margin:0;background:transparent;font-family:Arial,Helvetica,sans-serif;color:{INK}}}
.num{{width:46px;height:46px;border-radius:50%;background:{ORANGE};color:#fff;font-weight:700;font-size:24px;display:flex;align-items:center;justify-content:center;flex:none}}
.h{{font-weight:700;color:{NAVY}}}</style>"""


def qr_data_uri(url: str) -> str:
    img = qrcode.make(url, box_size=10, border=1)
    buf = io.BytesIO(); img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def render(name: str, html: str, w: int, h: int):
    f = OUT / f"{name}.html"
    f.write_text(html)
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=2",
                    "--default-background-color=00000000", f"--window-size={w},{h}", f"--screenshot={OUT / (name + '.png')}", f"file://{f}"],
                   check=True, capture_output=True)
    f.unlink()


# 1) the Sentinel loop (9.32in x 1.05in -> 932x105 css px)
steps = [("Inspect", "reads your IDE workspace"), ("Analyze", "deterministic readiness score"), ("Plan", "safe / confirm / manual"),
         ("Apply", "IDE actions, only after you say yes"), ("Verify", "re-read the IDE, before vs after")]
chips = ""
for i, (t, s) in enumerate(steps, 1):
    chips += (f'<div style="flex:1;display:flex;align-items:center;gap:10px;background:{CARD};border-radius:14px;padding:0 12px;height:105px">'
              f'<div class="num" style="width:38px;height:38px;font-size:20px">{i}</div><div><div class="h" style="font-size:19px">{t}</div>'
              f'<div style="font-size:12.5px;color:{MUTED};line-height:1.25;margin-top:3px">{s}</div></div></div>')
    if i < len(steps):
        chips += f'<div style="color:{ORANGE};font-size:24px;font-weight:700;width:22px;text-align:center;flex:none">&#10140;</div>'
render("flow", f'<html><head>{BASE}</head><body><div style="display:flex;align-items:center;width:932px;height:105px">{chips}</div></body></html>', 932, 105)

# 2) result tiles
tiles = [("35 &#8594; 65", "edge readiness, verified live", ORANGE), ("12", "findings resolved in one chat", TEAL),
         ("0", "changes without your explicit yes", NAVY), ("200+", "automated tests, Docker amd64", TEAL)]
t = ""
for big, small, c in tiles:
    t += (f'<div style="flex:1;background:{CARD};border-radius:14px;height:105px;padding:12px 14px;display:flex;flex-direction:column;justify-content:center">'
          f'<div style="font-size:38px;font-weight:800;color:{c};line-height:1">{big}</div><div style="font-size:14px;color:{MUTED};margin-top:7px;line-height:1.25">{small}</div></div>')
render("stats", f'<html><head>{BASE}</head><body><div style="display:flex;gap:12px;width:932px;height:105px">{t}</div></body></html>', 932, 105)

# 3) links with QR codes (9.32in x 2.0in)
links = [("Source code", "github.com/TusharTechs/<br>hyperion-sentinel", "https://github.com/TusharTechs/hyperion-sentinel"),
         ("Live demo", "youtu.be/<br>7AZYCdE_vZU", "https://youtu.be/7AZYCdE_vZU"),
         ("Docker image", "hub.docker.com/r/<br>tushartechs/hyperion", "https://hub.docker.com/r/tushartechs/hyperion")]
cards = ""
for title, shown, url in links:
    cards += (f'<div style="flex:1;background:{CARD};border-radius:14px;height:200px;display:flex;align-items:center;gap:14px;padding:0 14px">'
              f'<img src="{qr_data_uri(url)}" style="width:128px;height:128px;border-radius:6px;background:#fff;flex:none">'
              f'<div><div class="h" style="font-size:19px">{title}</div><div style="font-size:12.5px;color:{MUTED};margin-top:6px;line-height:1.35">{shown}</div>'
              f'<div style="font-size:12px;color:{ORANGE};font-weight:700;margin-top:8px">scan to open</div></div></div>')
render("links", f'<html><head>{BASE}</head><body><div style="display:flex;gap:12px;width:932px;height:200px">{cards}</div></body></html>', 932, 200)
print("assets:", sorted(p.name for p in OUT.glob("*.png")))
