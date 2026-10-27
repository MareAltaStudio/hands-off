"""Measure whether launch() leaves the focus where the user is.

Puts Paint in front on monitor 1 (with a real click, like a user), then launches each
program on monitor 2 and samples the foreground window for a few seconds. Run only
when nobody is using the PC.

    python launch_focus_test.py            # launch() as it is (WMI since 0.1.1)
    python launch_focus_test.py --popen    # the old plain child process, for comparison
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))
sys.path.insert(0, str(HERE))

from hands_off import server  # noqa: E402

user32 = ctypes.windll.user32
OUT = HERE / "out"


def fg_title() -> str:
    b = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(user32.GetForegroundWindow(), b, 256)
    return b.value


def paint_in_front() -> int:
    subprocess.Popen(["mspaint.exe"])
    end = time.time() + 20
    h = 0
    while time.time() < end and not h:
        time.sleep(0.5)
        h = next((w["hwnd"] for w in server._top_windows() if "Paint" in w["title"]), 0)
    user32.ShowWindow(h, 3)
    time.sleep(1.0)
    # the click comes from ANOTHER process: the one that sends input gets the right to set the
    # foreground, which would make this test easy for the focus guard
    subprocess.run([sys.executable, "-c", "import fake_user as f, time; f.move(1280, 760); time.sleep(0.2); "
                    "f.down(1280, 760); f.up(1280, 760)"], cwd=str(HERE))
    time.sleep(0.8)
    return h


def main() -> int:
    if "--popen" in sys.argv:  # the old way, for comparison
        server._spawn_without_focus = lambda *a, **k: None
    OUT.mkdir(exist_ok=True)
    note = OUT / "launch_test.txt"
    note.write_text("hands-off launch test\n")
    targets = [
        ("calc.exe", ""),
        ("charmap.exe", ""),
        ("notepad.exe", str(note)),
        (r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe", "--factory-startup"),
        (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
         "--guest --no-first-run --no-default-browser-check --new-window about:blank"),
    ]
    paint = paint_in_front()
    rows = []
    for cmd, args in targets:
        if "Paint" not in fg_title():
            paint_in_front()
        before = fg_title()
        r = server.launch(cmd, args, monitor=2, corner="top-right", wait_s=30)
        samples = []
        for _ in range(10):
            time.sleep(0.5)
            samples.append("Paint" in fg_title())
        hw = r.split()[1] if r.startswith("window ") else ""
        rows.append({"program": Path(cmd).name, "foreground_before": before[:40],
                     "kept_on_paint": all(samples), "samples_on_paint": f"{sum(samples)}/10",
                     "result": r.replace("\n", " | ")[:200]})
        print(json.dumps(rows[-1], ensure_ascii=False))
        if hw:
            server.close(hw)
            time.sleep(2)
    name = f"launch_focus_test{'_popen' if '--popen' in sys.argv else ''}.json"
    (OUT / name).write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(paint, ctypes.byref(pid))
    subprocess.run(["taskkill", "/PID", str(pid.value), "/F"], capture_output=True)
    ok = sum(r["kept_on_paint"] for r in rows)
    print(f"kept the focus on Paint: {ok}/{len(rows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
