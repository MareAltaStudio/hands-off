"""Probe: can hands-off browse a Chromium page on monitor 2 without taking the focus?

Opens Chrome as a guest (no profile, no sign-in prompts) at a URL, then scrolls with
keys and reports where the foreground was before and after each step. The window
number is printed so the next steps (click_xy on links) can be tried by hand.

    python browser_probe.py [url]
"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

from hands_off import server  # noqa: E402

user32 = ctypes.windll.user32
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
URL = "https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/subdivision_surface.html"


def fg() -> str:
    b = ctypes.create_unicode_buffer(200)
    user32.GetWindowTextW(user32.GetForegroundWindow(), b, 200)
    return b.value[:50]


def step(label, fn):
    before = fg()
    out = fn()
    time.sleep(0.8)
    print(f"{label}: {str(out).splitlines()[0][:110]}")
    print(f"   foreground {before!r} -> {fg()!r}")
    return out


def main() -> int:
    url = sys.argv[1] if len(sys.argv) > 1 else URL
    args = f"--guest --no-first-run --no-default-browser-check --new-window {url}"
    r = step("launch", lambda: server.launch(CHROME, args, monitor=2, corner="top-left", wait_s=30))
    h = r.split()[1]
    time.sleep(4)
    for _ in range(3):
        step("pagedown", lambda: server.keys(h, "pagedown"))
    print("window:", h)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
