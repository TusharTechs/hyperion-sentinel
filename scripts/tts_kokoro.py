"""Neural TTS with Kokoro (local, free). Usage: uv run --with kokoro-onnx --with soundfile python scripts/tts_kokoro.py <voice> <speed> out_dir [keys...]"""
import json
import pathlib
import sys

import soundfile as sf
from kokoro_onnx import Kokoro

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from video_script import NARRATION  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
MODELS = ROOT / "video" / "models"


def speak_text(key: str) -> str:
    """Natural spoken form (Kokoro reads real words better than the spelled-out letters used for macOS say)."""
    t = NARRATION[key]
    return (t.replace("HYPER A I I D E", "HYPER-AI IDE").replace("HYPER A I", "HYPER-AI").replace("I D E", "IDE").replace("R A G", "RAG"))


def main():
    voice, speed, out = sys.argv[1], float(sys.argv[2]), pathlib.Path(sys.argv[3])
    keys = sys.argv[4:] or list(NARRATION)
    out.mkdir(parents=True, exist_ok=True)
    k = Kokoro(str(MODELS / "kokoro-v1.0.onnx"), str(MODELS / "voices-v1.0.bin"))
    durs = {}
    for key in keys:
        samples, sr = k.create(speak_text(key), voice=voice, speed=speed, lang="en-us")
        sf.write(out / f"{key}.wav", samples, sr)
        durs[key] = round(len(samples) / sr, 2)
        print(key, durs[key], flush=True)
    (out / "durations.json").write_text(json.dumps(durs, indent=1))


if __name__ == "__main__":
    main()
