"""Render the submission deck to PDF with headless Chrome (no LibreOffice needed).

Reproduces the Veles Hack template's geometry (10 x 5.625 in): backgrounds, logos, footer band, title/body boxes. Content comes from
scripts/build_pptx.py so the PDF and the PPTX cannot drift apart.
Usage: python3 scripts/make_pdf.py <template.pptx> <out.pdf>
"""
import html
import pathlib
import shutil
import subprocess
import sys
import tempfile
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from build_pptx import DOCKER, GITHUB, HIGHLIGHTS, SUMMARY, VIDEO  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "ppt"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
NAVY = "#25346A"


def box(x, y, w, h, inner, style=""):
    return f'<div class="abs" style="left:{x}in;top:{y}in;width:{w}in;height:{h}in;{style}">{inner}</div>'


def img(src, x, y, w, h, alt=""):
    return f'<img class="abs" src="{src}" alt="{html.escape(alt)}" style="left:{x}in;top:{y}in;width:{w}in;height:{h}in">'


def bullets(items):
    out = ""
    for label, body, link in items:
        text = f"<b>{html.escape(label)}</b>" if label else ""
        if link:
            text += f'<a href="{link[0]}">{html.escape(link[1])}</a>'
        if body:
            text += html.escape(body)
        out += f"<li>{text}</li>"
    return f"<ul>{out}</ul>"


def footer(n):
    return (img("media/image6.png", 0, 5.19, 10, 0.43) + img("media/image3.png", 3.18, 5.28, 3.64, 0.3) +
            img("media/image7.png", 0.34, 5.22, 0.64, 0.38) + img("media/image1.png", 7.68, 5.24, 1.58, 0.35) +
            box(9.27, 5.24, 0.6, 0.35, str(n), "color:#fff;font-size:10pt;text-align:right;display:flex;align-items:center;justify-content:flex-end;padding-right:.1in"))


def content_slide(n, title, body_items, body_h, picture):
    return (f'<section class="slide">{img("media/image9.png", 0, 0.43, 0.34, 0.74)}'
            + box(0.34, 0.49, 9.32, 0.63, html.escape(title), f"padding:.1in;font:700 24pt Roboto,'Helvetica Neue',Arial,sans-serif;color:{NAVY};line-height:1")
            + box(0.34, 1.26, 9.32, body_h, bullets(body_items), "padding:.1in;font:14pt Arial,Helvetica,sans-serif;color:#000")
            + picture + footer(n) + "</section>")


def build_html(media_dir_rel: str) -> str:
    s1 = (f'<section class="slide">{img("media/image5.jpg", 0, 0, 10.01, 5.63)}{img("media/image3.png", 7.28, 1.65, 2.49, 0.21)}'
          f'{img("media/image8.png", 7.28, 0.21, 2.26, 1.42)}{img("media/image2.png", 8.31, 5.17, 1.54, 0.34)}'
          + box(0.51, 3.39, 7.64, 1.0, "Hyperion Sentinel", "padding:.1in;font:400 40pt Roboto,'Helvetica Neue',Arial,sans-serif;color:#fff")
          + box(0.51, 4.15, 8.86, 1.09, '<div style="font:500 22pt Roboto,\'Helvetica Neue\',Arial,sans-serif">The edge-readiness engineer inside the HYPER-AI IDE</div>'
                '<div style="font:400 14pt Roboto,\'Helvetica Neue\',Arial,sans-serif">Veles Hack 2026&nbsp;&nbsp;|&nbsp;&nbsp;Challenge 1: Hyperion, an LLM-powered agentic assistant</div>',
                "padding:.1in;color:#fff;display:flex;flex-direction:column;justify-content:center") + "</section>")
    links = [("GitHub repo: ", None, (GITHUB, GITHUB)), ("Docker image: ", None, (DOCKER, DOCKER)),
             ("Demo video (2 min, recorded live in the real IDE): ", None, (VIDEO, VIDEO))]
    s2 = content_slide(2, "GitHub repo", links, 1.25, img("../../../assets/ppt/links.png", 0.44, 2.85, 9.12, 9.12 * 400 / 1864, "QR codes"))
    strip = lambda f: img(f"../../../assets/ppt/{f}", 0.44, 3.97, 9.12, 9.12 * 210 / 1864)  # noqa: E731
    s3 = content_slide(3, "Summary", [(a, b, None) for a, b in SUMMARY], 2.7, strip("flow.png"))
    s4 = content_slide(4, "Highlights", [(a, b, None) for a, b in HIGHLIGHTS], 2.7, strip("stats.png"))
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Hyperion Sentinel - Veles Hack 2026 submission</title>
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=swap" rel="stylesheet">
<style>
@page {{ size: 10in 5.625in; margin: 0 }}
* {{ box-sizing: border-box }} html, body {{ margin: 0; background: #fff }}
.slide {{ position: relative; width: 10in; height: 5.625in; overflow: hidden; background: #fff; page-break-after: always; break-after: page }}
.slide:last-child {{ page-break-after: auto; break-after: auto }}
.abs {{ position: absolute }}
ul {{ margin: 0; padding: 0; list-style: none }}
li {{ position: relative; margin: 0 0 2pt 0; padding-left: .5in; line-height: 1.38 }}
li::before {{ content: "\\25CF"; position: absolute; left: .153in; font-size: 14pt; color: #444 }}
a {{ color: #1155cc; text-decoration: underline }}
</style></head><body>{s1}{s2}{s3}{s4}</body></html>"""


def main(template: str, out: str):
    work = pathlib.Path(tempfile.mkdtemp(dir=ROOT / "video"))
    try:
        with zipfile.ZipFile(template) as z:
            z.extractall(work / "t")
        d = work / "x" / "y" / "z"        # so ../../../assets/ppt resolves inside this scratch tree
        d.mkdir(parents=True)
        (work / "assets").mkdir()
        shutil.copytree(ASSETS, work / "assets" / "ppt")
        shutil.copytree(work / "t" / "ppt" / "media", d / "media")
        page = d / "deck.html"
        page.write_text(build_html("media"), encoding="utf-8")
        subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", "--virtual-time-budget=8000",
                        f"--print-to-pdf={pathlib.Path(out).resolve()}", f"file://{page}"], check=True, capture_output=True)
        # also keep an HTML copy for visual QA
        shutil.copy(page, work / "preview.html")
        shutil.copytree(work / "assets", d / "assets", dirs_exist_ok=True)
        print("wrote", out)
        return work
    except Exception:
        shutil.rmtree(work, ignore_errors=True)
        raise


if __name__ == "__main__":
    w = main(sys.argv[1], sys.argv[2])
    print("scratch:", w)
