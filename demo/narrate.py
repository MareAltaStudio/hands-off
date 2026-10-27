"""Narration for the demo video through a local Voicebox (Kokoro voices).

    uv run --no-project --with requests python narrate.py samples am_michael af_heart am_fenrir bm_george
    uv run --no-project --with requests python narrate.py full af_heart          # -> out/demo_narrated.mp4

Each voice gets a Voicebox profile named "hands-off demo · <voice>" (preset, Kokoro), so the
user's own profiles are left alone. `personality` is off: Voicebox's small LLM would reword
the line otherwise. Lines are placed at fixed times (seconds into the 35-s video) and the
video is muxed with the narration, no re-encode.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from voicebox_api import BASE, DATA, ensure  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"

SAMPLE = "This is hands-off. On the left, someone working in Blender: the real cursor, moved by a script."
# (start second, line): kept in step with the captions (8, 16, 24 s) and the end card (30 s)
SCRIPT = [
    (0.4, "This is hands-off."),
    (3.4, "On the left, someone working in Blender: the real cursor, moved by a script."),
    (9.6, "On the right, Claude is reading the Blender manual, clicking through a browser on the other screen."),
    (17.4, "It never touches the mouse, the keyboard, or the focus. Blender stays in front the whole time."),
    (25.6, "One take. No cuts."),
    (30.0, "hands-off: an MCP server for Windows. Your mouse stays yours."),
]


def profile_for(voice: str) -> str:
    name = f"hands-off demo · {voice}"
    for p in requests.get(f"{BASE}/profiles", timeout=10).json():
        if p["name"] == name:
            return p["id"]
    r = requests.post(f"{BASE}/profiles", timeout=20, json={
        "name": name, "language": "en", "voice_type": "preset", "preset_engine": "kokoro",
        "preset_voice_id": voice, "default_engine": "kokoro"})
    r.raise_for_status()
    return r.json()["id"]


def speak(voice: str, text: str, dest: Path) -> Path:
    r = requests.post(f"{BASE}/generate", timeout=120, json={
        "profile_id": profile_for(voice), "text": text, "language": "en", "engine": "kokoro",
        "personality": False, "normalize": True})
    r.raise_for_status()
    gid = r.json()["id"]
    end = time.time() + 120
    while time.time() < end:  # /generate answers before the audio exists
        h = requests.get(f"{BASE}/history/{gid}", timeout=10).json()
        src = os.path.join(DATA, h.get("audio_path") or "")
        if h.get("audio_path") and os.path.isfile(src):
            time.sleep(0.3)
            shutil.copyfile(src, dest)
            return dest
        time.sleep(0.3)
    raise RuntimeError(f"no audio for {text!r}")


def ffmpeg() -> str:
    out = subprocess.run(["uvx", "--from", "imageio-ffmpeg", "python", "-c",
                          "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip().splitlines()[-1]


def duration(ff: str, wav: Path) -> float:
    import re
    info = subprocess.run([ff, "-hide_banner", "-i", str(wav)], capture_output=True, text=True).stderr
    h, m, s = re.search(r"Duration: (\d+):(\d+):([\d.]+)", info).groups()
    return int(h) * 3600 + int(m) * 60 + float(s)


def main() -> int:
    ensure()
    OUT.mkdir(exist_ok=True)
    mode, voices = sys.argv[1], sys.argv[2:]
    if mode == "samples":
        for v in voices:
            print(speak(v, SAMPLE, OUT / f"voice_{v}.wav"))
        return 0
    voice = voices[0]
    ff = ffmpeg()
    parts = []
    for i, (start, line) in enumerate(SCRIPT):
        wav = speak(voice, line, OUT / f"line_{i}.wav")
        d = duration(ff, wav)
        nxt = SCRIPT[i + 1][0] if i + 1 < len(SCRIPT) else 35.0
        flag = "" if start + d <= nxt else f"  <-- runs {start + d - nxt:.1f}s into the next line"
        print(f"{start:5.1f}s +{d:4.1f}s  {line}{flag}")
        parts.append((start, wav))
    inputs = sum((["-i", str(w)] for _, w in parts), [])
    delays = ";".join(f"[{i}:a]adelay={int(s * 1000)}|{int(s * 1000)}[a{i}]" for i, (s, _) in enumerate(parts))
    mix = "".join(f"[a{i}]" for i in range(len(parts))) + f"amix=inputs={len(parts)}:normalize=0,apad=whole_dur=35[a]"
    narration = OUT / "narration.wav"
    subprocess.run([ff, "-y", "-loglevel", "error", *inputs, "-filter_complex", f"{delays};{mix}", "-map", "[a]",
                    "-t", "35", str(narration)], check=True)
    final = OUT / "demo_narrated.mp4"
    subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(OUT / "demo.mp4"), "-i", str(narration),
                    "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest",
                    "-movflags", "+faststart", str(final)], check=True)
    print("done:", final)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
