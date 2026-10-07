"""Fill the Veles Hack submission template (slides: title, GitHub repo, Summary, Highlights).

Edits the template's XML in place (keeps its layouts/branding), adds hyperlinks and three graphics, and checks text fit with real
Arial metrics. Run: uv run --with pillow python scripts/build_pptx.py <template.pptx> <out.pptx>
"""
import pathlib
import re
import shutil
import sys
import tempfile
import zipfile
from xml.sax.saxutils import escape

from PIL import ImageFont

ROOT = pathlib.Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets" / "ppt"
EMU = 914400
BODY_H = 2468880        # 2.7in body placeholder on slides 3-4
STRIP_Y = 3630168       # 3.97in graphic strip below it
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"
ARIAL_B = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

GITHUB = "https://github.com/TusharTechs/hyperion-sentinel"
VIDEO = "https://youtu.be/7AZYCdE_vZU"
DOCKER = "https://hub.docker.com/r/tushartechs/hyperion"

# --------------------------------------------------------------------------- content
SUMMARY = [
    ("What: ", "an agentic assistant for the HYPER-AI IDE. You chat; it inspects your workspace and acts through IDE actions (create / edit / delete files)."),
    ("Problem: ", "edge deployments fail on the basics: latest images, no limits or probes, root, secrets in config."),
    ("Solution: ", "a deterministic Edge Readiness analyzer finds and scores issues; the LLM only converses."),
    ("Loop: ", "inspect, plan, you approve, apply via the IDE, re-read: before vs after."),
    ("Criteria: ", "guardrails, RAG on the official docs, memory, human-in-the-loop."),
]
HIGHLIGHTS = [
    ("Verified live ", "in the real IDE with Llama 3.1: readiness 35 to 65, 12 findings fixed."),
    ("Deterministic: ", "the LLM never sets scores or findings; secrets are never printed."),
    ("Safe by design: ", "every delete, overwrite and plan needs an explicit yes; guardrails fail closed."),
    ("Grounded + memory: ", "RAG with sources; per-user memory (\"fix the second issue\")."),
    ("Robust: ", "works without an IDE backend or API key; 200+ tests; non-root amd64 image."),
    ("Open source ", "(Apache-2.0): GitHub, Docker Hub, 2-minute live demo video."),
]

# --------------------------------------------------------------------------- helpers
def text_lines(parts, pt, width_pt):
    """Count wrapped lines for runs [(text, bold)] at `pt` Arial in `width_pt`."""
    reg, bold = ImageFont.truetype(ARIAL, 200), ImageFont.truetype(ARIAL_B, 200)
    words = []
    for t, b in parts:
        for w in re.findall(r"\S+\s*", t):
            words.append((w, b))
    lines, cur = 1, 0.0
    for w, b in words:
        wpt = (bold if b else reg).getlength(w) * pt / 200
        if cur + (bold if b else reg).getlength(w.rstrip()) * pt / 200 > width_pt and cur > 0:
            lines += 1; cur = 0.0
        cur += wpt
    return lines


def fit_report(name, items, pt, box_w_emu, box_h_emu, marl_emu=457200, inset_pt=7.2, lnspc=1.15, spc_after=2):
    width_pt = box_w_emu / 12700 - 2 * inset_pt - marl_emu / 12700
    total = sum(text_lines([(a, True), (b, False)], pt, width_pt) for a, b in items)
    height_pt = total * pt * 1.2 * lnspc + len(items) * spc_after + 2 * inset_pt
    box_pt = box_h_emu / 12700
    ok = height_pt <= box_pt
    print(f"{name}: {total} lines @ {pt}pt -> {height_pt:.0f}pt of {box_pt:.0f}pt  {'OK' if ok else 'OVERFLOW'}")
    return ok


def para(label, body, sz=None, bullet=True, link=None):
    """One bullet paragraph in the template's body style (copy of the template pPr)."""
    szattr = f' sz="{sz}"' if sz else ""
    ppr = ('<a:pPr indent="-317500" lvl="0" marL="457200" rtl="0" algn="l"><a:lnSpc><a:spcPct val="115000"/></a:lnSpc><a:spcBef><a:spcPts val="0"/></a:spcBef>'
           '<a:spcAft><a:spcPts val="200"/></a:spcAft><a:buSzPts val="1400"/><a:buChar char="&#9679;"/></a:pPr>')
    runs = ""
    if label:
        runs += f'<a:r><a:rPr lang="en" b="1"{szattr}/><a:t>{escape(label)}</a:t></a:r>'
    if link:
        runs += (f'<a:r><a:rPr lang="en"{szattr}><a:hlinkClick r:id="{link[0]}"/></a:rPr><a:t>{escape(link[1])}</a:t></a:r>')
    if body:
        runs += f'<a:r><a:rPr lang="en"{szattr}/><a:t>{escape(body)}</a:t></a:r>'
    return f"<a:p>{ppr}{runs}<a:endParaRPr/></a:p>"


def pic(shape_id, name, alt, rid, x, y, w, h):
    return (f'<p:pic><p:nvPicPr><p:cNvPr id="{shape_id}" name="{name}" descr="{escape(alt, {chr(34): "&quot;"})}"/><p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr><p:nvPr/></p:nvPicPr>'
            f'<p:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></p:blipFill>'
            f'<p:spPr><a:xfrm><a:off x="{x}" y="{y}"/><a:ext cx="{w}" cy="{h}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></p:spPr></p:pic>')


def set_body(xml, paras_xml, cy_emu=None):
    """Replace the body placeholder's paragraphs (and optionally its height)."""
    m = re.search(r'(<p:sp><p:nvSpPr><p:cNvPr id="\d+" name="[^"]*"/><p:cNvSpPr txBox="1"/><p:nvPr><p:ph idx="1" type="body"/></p:nvPr></p:nvSpPr>.*?<a:lstStyle/>)(.*?)(</p:txBody></p:sp>)', xml, re.S)
    assert m, "body placeholder not found"
    new = m.group(1) + paras_xml + m.group(3)
    if cy_emu:
        new = re.sub(r'(<a:ext cx="\d+" cy=")\d+(")', rf"\g<1>{cy_emu}\g<2>", new, count=1)
    return xml[: m.start()] + new + xml[m.end():]


def add_rel(rels_xml, rid, rtype, target, external=False):
    mode = ' TargetMode="External"' if external else ""
    return rels_xml.replace("</Relationships>", f'<Relationship Id="{rid}" Type="{rtype}" Target="{escape(target)}"{mode}/></Relationships>')


IMG = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image"
HLK = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink"


def main(template: str, out: str):
    ok = all([
        fit_report("Summary", SUMMARY, 14, 8520600, BODY_H),
        fit_report("Highlights", HIGHLIGHTS, 14, 8520600, BODY_H),
    ])
    if not ok:
        sys.exit("text does not fit at the template's 14pt - shorten the copy")
    sz = None

    work = pathlib.Path(tempfile.mkdtemp())
    with zipfile.ZipFile(template) as z:
        z.extractall(work)
    ppt = work / "ppt"
    for n, f in (("hs_flow.png", "flow.png"), ("hs_stats.png", "stats.png"), ("hs_links.png", "links.png")):
        shutil.copy(ASSETS / f, ppt / "media" / n)

    def rd(p): return (ppt / p).read_text(encoding="utf-8")
    def wr(p, s): (ppt / p).write_text(s, encoding="utf-8")

    left = 402336            # 0.44in: aligns with the body text inset
    strip_w = 8339328        # 9.12in
    strip_h = int(strip_w * 210 / 1864)

    # ---- slide 1: title
    s1 = rd("slides/slide1.xml")
    s1 = s1.replace("<a:t>Project_Name</a:t>", "<a:t>Hyperion Sentinel</a:t>")
    sub_old = re.search(r'(<p:ph idx="1" type="subTitle"/>.*?<a:lstStyle/>)(.*?)(</p:txBody>)', s1, re.S)
    sub_pp = '<a:pPr indent="0" lvl="0" marL="0" rtl="0" algn="l"><a:lnSpc><a:spcPct val="100000"/></a:lnSpc><a:spcBef><a:spcPts val="0"/></a:spcBef><a:spcAft><a:spcPts val="0"/></a:spcAft><a:buNone/></a:pPr>'
    sub_new = (f'<a:p>{sub_pp}<a:r><a:rPr lang="en" sz="2200"/><a:t>The edge-readiness engineer inside the HYPER-AI IDE</a:t></a:r></a:p>'
               f'<a:p>{sub_pp}<a:r><a:rPr lang="en" sz="1400"><a:solidFill><a:schemeClr val="lt1"/></a:solidFill></a:rPr><a:t>Veles Hack 2026  |  Challenge 1: Hyperion, an LLM-powered agentic assistant</a:t></a:r></a:p>')
    s1 = s1[: sub_old.start(2)] + sub_new + s1[sub_old.end(2):]
    s1 = s1.replace('<a:off x="464100" y="3794075"/><a:ext cx="7516500" cy="795600"/>', '<a:off x="464100" y="3794075"/><a:ext cx="8100000" cy="1000000"/>')
    wr("slides/slide1.xml", s1)

    # ---- slide 2: GitHub repo (+ links graphic)
    s2 = rd("slides/slide2.xml")
    paras2 = (para("GitHub repo: ", None, link=("rId20", GITHUB)) +
              para("Docker image: ", None, link=("rId22", DOCKER)) +
              para("Demo video (2 min, recorded live in the real IDE): ", None, link=("rId21", VIDEO)))
    s2 = set_body(s2, paras2, cy_emu=1143000)
    pic2 = pic(100, "Links", "QR codes for the source code, the live demo video and the Docker image", "rId23", left, 2606040, strip_w, int(strip_w * 400 / 1864))
    s2 = s2.replace("</p:spTree>", pic2 + "</p:spTree>")
    wr("slides/slide2.xml", s2)
    r2 = rd("slides/_rels/slide2.xml.rels")
    for rid, url in (("rId20", GITHUB), ("rId21", VIDEO), ("rId22", DOCKER)):
        r2 = add_rel(r2, rid, HLK, url, external=True)
    r2 = add_rel(r2, "rId23", IMG, "../media/hs_links.png")
    wr("slides/_rels/slide2.xml.rels", r2)

    # ---- slides 3 and 4
    for num, items, media, alt in ((3, SUMMARY, "hs_flow.png", "The Sentinel loop: inspect, analyze, plan, apply, verify"),
                                   (4, HIGHLIGHTS, "hs_stats.png", "Results: edge readiness 35 to 65, 12 findings resolved, 0 changes without a yes, 200+ tests")):
        s = rd(f"slides/slide{num}.xml")
        s = set_body(s, "".join(para(a, b, sz=sz) for a, b in items), cy_emu=BODY_H)
        s = s.replace("</p:spTree>", pic(100, "Graphic", alt, "rId20", left, STRIP_Y, strip_w, strip_h) + "</p:spTree>")
        wr(f"slides/slide{num}.xml", s)
        r = add_rel(rd(f"slides/_rels/slide{num}.xml.rels"), "rId20", IMG, f"../media/{media}")
        wr(f"slides/_rels/slide{num}.xml.rels", r)

    outp = pathlib.Path(out)
    if outp.exists():
        outp.unlink()
    with zipfile.ZipFile(outp, "w", zipfile.ZIP_DEFLATED) as z:
        # [Content_Types].xml must be first
        z.write(work / "[Content_Types].xml", "[Content_Types].xml")
        for p in sorted(work.rglob("*")):
            if p.is_file() and p.name != "[Content_Types].xml":
                z.write(p, p.relative_to(work).as_posix())
    shutil.rmtree(work)
    print("wrote", outp)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
