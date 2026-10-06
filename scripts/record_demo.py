"""Record the live demo: drives the REAL HYPER-AI IDE (http://localhost:5050) against the REAL agent.

Frames come from Chrome's screencast (CDP), so no extra recorder is needed.
Requires: ide-backend + ide-gui + Hyperion running, Chrome installed, `uv run --with playwright`.
Outputs video/live.mp4 (constant 20 fps, encoded on the fly) and video/steps.json (step start/end seconds).
"""
import base64
import json
import pathlib
import subprocess
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from playwright.sync_api import sync_playwright  # noqa: E402

from video_script import E2E_CONFIRM_NO, LIVE_STEPS  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "video"
FPS = 20
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DUR = json.loads((OUT / "audio" / "durations.json").read_text())
URL = "http://localhost:5050/"

CAPTION_JS = """
(text) => {
  let el = document.getElementById('demo-cap');
  if (!el) {
    el = document.createElement('div'); el.id = 'demo-cap';
    el.style.cssText = 'position:fixed;left:64px;bottom:34px;z-index:99999;padding:10px 18px;border-radius:12px;' +
      'background:rgba(7,11,22,.88);border:1px solid rgba(94,234,212,.55);color:#99F6E4;font:600 20px/1.2 -apple-system,Helvetica,Arial,sans-serif;' +
      'box-shadow:0 6px 24px rgba(0,0,0,.45);letter-spacing:.2px';
    document.body.appendChild(el);
  }
  el.innerHTML = '<span style="color:#F87171">&#9679; LIVE</span> &nbsp;' + text;
}
"""
LAST_AGENT_JS = """() => { const m=[...document.querySelectorAll('.agent-msg.agent')]; const l=m[m.length-1]; return l ? [m.length, l.innerText.length, l.innerText.slice(-160)] : [0,0,'']; }"""
SCROLL_TOP_OF_LAST_JS = """() => { const m=[...document.querySelectorAll('.agent-msg.agent')]; const l=m[m.length-1]; if(l){ l.scrollIntoView({block:'start'}); } }"""


def main():
    OUT.mkdir(exist_ok=True)
    live_mp4 = OUT / "live.mp4"
    ff = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-c:v", "mjpeg", "-framerate", str(FPS), "-i", "-",
                           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), str(live_mp4)],
                          stdin=subprocess.PIPE)
    state = {"prev": None, "t_prev": None, "written": 0}
    first_wall: list[float] = []

    def emit(jpeg: bytes, until_t: float):
        """Write the previous frame enough times to hold it until `until_t` (constant frame rate)."""
        if state["prev"] is None:
            return
        want = int(round((until_t - state["t0"]) * FPS))
        while state["written"] < want:
            ff.stdin.write(state["prev"]); state["written"] += 1

    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROME, headless=True, args=["--hide-scrollbars"])
        ctx = browser.new_context(viewport={"width": 1600, "height": 900}, device_scale_factor=1)
        page = ctx.new_page()
        cdp = ctx.new_cdp_session(page)

        def on_frame(ev):
            jpeg = base64.b64decode(ev["data"])
            ts = ev["metadata"]["timestamp"]
            if state["prev"] is None:
                first_wall.append(time.time()); state["t0"] = ts
            else:
                emit(state["prev"], ts)  # hold the previous picture until this frame's time
            state["prev"] = jpeg
            try:
                cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            except Exception:
                pass
            state["last_ts"] = ts

        cdp.on("Page.screencastFrame", on_frame)
        page.goto(URL)
        page.wait_for_timeout(1200)
        cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 1600, "maxHeight": 900, "everyNthFrame": 1})
        t_start = time.time()
        rel = lambda: time.time() - t_start  # noqa: E731

        page.evaluate(CAPTION_JS, "real HYPER-AI IDE  ·  real agent  ·  real Llama 3.1")
        page.wait_for_timeout(900)
        page.click('button[title="Hyperion Agent"]')
        page.wait_for_timeout(500)
        # widen the chat panel so the report is readable
        box = page.locator(".agent-resizer").bounding_box()
        page.mouse.move(box["x"] + 2, box["y"] + 200)
        page.mouse.down(); page.mouse.move(box["x"] - 330, box["y"] + 200, steps=12); page.mouse.up()
        page.wait_for_timeout(500)
        inp = page.locator('textarea[placeholder="Message the agent..."]')

        steps_out = []

        def run_step(key, caption, message, must_contain=None, scroll_top=False, extra_dwell=0.8):
            t0 = rel()
            page.evaluate(CAPTION_JS, caption)
            page.wait_for_timeout(350)
            inp.click()
            inp.type(message, delay=26)
            page.wait_for_timeout(250)
            before = page.evaluate(LAST_AGENT_JS)[0]
            page.keyboard.press("Enter")
            # wait for a new agent message, then for it to stop changing
            deadline = time.time() + 90
            last, stable_since = None, time.time()
            while time.time() < deadline:
                page.wait_for_timeout(250)
                cnt, ln, tail = page.evaluate(LAST_AGENT_JS)
                state = (cnt, ln)
                if state != last:
                    last, stable_since = state, time.time()
                done = cnt > before and time.time() - stable_since > 2.4 and (must_contain is None or must_contain in tail or must_contain in page.evaluate("()=>[...document.querySelectorAll('.agent-msg.agent')].pop().innerText"))
                if done:
                    break
            if scroll_top:
                page.evaluate(SCROLL_TOP_OF_LAST_JS)
            # dwell so narration can finish
            need = DUR.get(key, 0) + extra_dwell
            while rel() - t0 < need:
                page.wait_for_timeout(150)
            steps_out.append({"key": key, "start": t0, "end": rel(), "message": message})
            print(f"step {key}: {t0:5.1f}s -> {rel():5.1f}s  ({message!r})", flush=True)

        specs = {
            "live1": dict(must_contain="Edge Readiness", scroll_top=True),
            "live2": dict(must_contain="Say \"fix #"),
            "live3": dict(must_contain="Nothing has been changed yet", scroll_top=True),
            "live4": dict(must_contain="Still open", scroll_top=True, extra_dwell=1.5),
            "live5": dict(must_contain="Sources"),
            "live6": dict(must_contain="focused on helping"),
            "live7": dict(must_contain="Reply \"yes\" to confirm"),
        }
        for key, caption, message in LIVE_STEPS:
            run_step(key, caption, message, **specs.get(key, {}))
        # decline the deletion so nothing else changes
        inp.click(); inp.type(E2E_CONFIRM_NO, delay=40); page.keyboard.press("Enter")
        page.wait_for_timeout(2200)
        end = rel()
        cdp.send("Page.stopScreencast")
        ctx.close(); browser.close()

    emit(state["prev"], state["last_ts"] + 0.6)
    ff.stdin.close(); ff.wait()
    off = first_wall[0] - t_start  # steps were timed from t_start; frames from the first frame
    for st in steps_out:
        st["start"] -= off; st["end"] -= off
    json.dump({"steps": steps_out, "recording_seconds": end - off}, (OUT / "steps.json").open("w"), indent=1)
    print(f"live.mp4 written, {end - off:.1f}s")


if __name__ == "__main__":
    main()
