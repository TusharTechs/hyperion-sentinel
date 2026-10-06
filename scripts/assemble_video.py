"""Assemble the demo video: scene slides + the live IDE recording + voiceover + subtitles.

Usage: uv run python scripts/assemble_video.py     (needs video/live.mp4, video/steps.json, video/audio/*.wav)
Output: video/hyperion-sentinel-demo.mp4 and .srt
"""
import json
import pathlib
import re
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from video_script import LIVE_STEPS, NARRATION  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
V = ROOT / "video"
SL = ROOT / "assets" / "slides"
FPS = 20
D = json.loads((V / "audio" / "durations.json").read_text())
STEPS = {s["key"]: s for s in json.loads((V / "steps.json").read_text())["steps"]}
LIVE_LEN = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(V / "live.mp4")]).strip())
LEAD, TAIL, FADE = 0.35, 0.45, 0.30

# scenes: (kind, source, narration key, duration)
scenes = [
    ("image", SL / "5-problem.png", "problem", D["problem"] + LEAD + TAIL),
    ("image", SL / "6-impact.png", "impact", D["impact"] + LEAD + TAIL),
    ("image", SL / "2-architecture.png", "how", D["how"] + LEAD + TAIL),
    ("live", V / "live.mp4", None, LIVE_LEN),
    ("image", SL / "7-close.png", "close", D["close"] + LEAD + 1.2),
]

inputs, vf, af, vlabels, alabels = [], [], [], [], []
n = 0
timeline = 0.0
cues = []  # (start, end, text)


def sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.:?!])\s+", text.replace(" I D E", " IDE").replace("HYPER A I", "HYPER-AI").replace("R A G", "RAG")) if s.strip()]


def add_cues(key, start):
    parts = sentences(NARRATION[key])
    total = sum(len(p) for p in parts)
    t = start
    for p in parts:
        d = D[key] * len(p) / total
        cues.append((t, t + d, p)); t += d


for kind, src, key, dur in scenes:
    if kind == "image":
        inputs += ["-loop", "1", "-framerate", str(FPS), "-t", f"{dur:.3f}", "-i", str(src)]
    else:
        inputs += ["-i", str(src)]
    vi = n
    n += 1
    vf.append(f"[{vi}:v]scale=1600:900:force_original_aspect_ratio=decrease,pad=1600:900:(ow-iw)/2:(oh-ih)/2:color=0x070B16,setsar=1,fps={FPS},"
              f"format=yuv420p,fade=t=in:st=0:d={FADE},fade=t=out:st={dur - FADE:.3f}:d={FADE}[v{vi}]")
    vlabels.append(f"[v{vi}]")
    # ---- audio for this scene
    if kind == "image":
        inputs += ["-i", str(V / "audio" / f"{key}.wav")]
        ai = n
        n += 1
        af.append(f"[{ai}:a]adelay={int(LEAD * 1000)}:all=1,apad=whole_dur={dur:.3f},atrim=0:{dur:.3f}[a{vi}]")
        add_cues(key, timeline + LEAD)
    else:
        mix = []
        for skey, _cap, _msg in LIVE_STEPS:
            inputs += ["-i", str(V / "audio" / f"{skey}.wav")]
            ai = n
            n += 1
            start = max(0.0, STEPS[skey]["start"] + 0.3)
            af.append(f"[{ai}:a]adelay={int(start * 1000)}:all=1[s{ai}]")
            mix.append(f"[s{ai}]")
            add_cues(skey, timeline + start)
        af.append("".join(mix) + f"amix=inputs={len(mix)}:normalize=0:dropout_transition=0,apad=whole_dur={dur:.3f},atrim=0:{dur:.3f}[a{vi}]")
    alabels.append(f"[a{vi}]")
    timeline += dur

total = timeline
graph = ";".join(vf + af) + ";" + "".join(vlabels) + f"concat=n={len(scenes)}:v=1:a=0[vout];" + "".join(alabels) + \
    f"concat=n={len(scenes)}:v=0:a=1,loudnorm=I=-16:TP=-1.5:LRA=9[aout]"

# subtitles
def ts(t):
    h, m, s = int(t // 3600), int(t % 3600 // 60), t % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

srt = V / "hyperion-sentinel-demo.srt"
srt.write_text("\n".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n" for i, (a, b, t) in enumerate(cues, 1)))

out = V / "hyperion-sentinel-demo.mp4"
cmd = ["ffmpeg", "-y", "-loglevel", "error", *inputs, "-i", str(srt), "-filter_complex", graph, "-map", "[vout]", "-map", "[aout]",
       "-map", f"{n}:s", "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k",
       "-c:s", "mov_text", "-metadata:s:s:0", "language=eng", "-movflags", "+faststart", str(out)]
subprocess.run(cmd, check=True)
print(f"wrote {out}  total {total:.1f}s  ({int(total // 60)}:{int(total % 60):02d})  cues={len(cues)}")
