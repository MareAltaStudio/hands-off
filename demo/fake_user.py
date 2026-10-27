"""The "user" of the demo video: a script that moves the REAL cursor and draws in Paint.

This is the only file in the project that uses synthetic input (SendInput), and it does
so on purpose: it plays the person who keeps working while the agent drives other
programs. If hands-off ever moved the cursor or took the focus, the line drawn here
would break, and the focus log would show it.

Safety: press Esc, or move the mouse yourself, and it lets go of the button and stops.

    python fake_user.py --seconds 32 --log out/focus_log.jsonl --t0-file out/t0.txt
    python fake_user.py --dry-run          # prints the path, touches nothing
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import sys
import time
from ctypes import wintypes
from pathlib import Path

user32 = ctypes.windll.user32
ctypes.windll.shcore.SetProcessDpiAwareness(2)

INPUT_MOUSE = 0
MOVE, LEFTDOWN, LEFTUP, ABSOLUTE, VIRTUALDESK = 0x0001, 0x0002, 0x0004, 0x8000, 0x4000
VK_ESCAPE = 0x1B


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("pad", ctypes.c_byte * 32)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wintypes.DWORD), ("u", _U)]


def _virtual_desk():
    return (user32.GetSystemMetrics(76), user32.GetSystemMetrics(77),   # SM_X/YVIRTUALSCREEN
            user32.GetSystemMetrics(78), user32.GetSystemMetrics(79))   # SM_CX/CYVIRTUALSCREEN


VX, VY, VW, VH = _virtual_desk()


def _send(flags: int, x: int = 0, y: int = 0) -> None:
    nx = round((x - VX) * 65535 / (VW - 1))
    ny = round((y - VY) * 65535 / (VH - 1))
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(nx, ny, 0, flags | ABSOLUTE | VIRTUALDESK, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def move(x: int, y: int) -> None:
    _send(MOVE, x, y)


def down(x: int, y: int) -> None:
    _send(MOVE | LEFTDOWN, x, y)


def up(x: int, y: int) -> None:
    _send(MOVE | LEFTUP, x, y)


def cursor() -> tuple[int, int]:
    p = wintypes.POINT()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


def foreground_title() -> str:
    h = user32.GetForegroundWindow()
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(h, buf, 256)
    return buf.value


def primary_rect() -> tuple[int, int, int, int]:
    return 0, 0, user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)


MIDDLEDOWN, MIDDLEUP, WHEEL = 0x0020, 0x0040, 0x0800


def wheel(x: int, y: int, notches: int) -> None:
    nx = round((x - VX) * 65535 / (VW - 1))
    ny = round((y - VY) * 65535 / (VH - 1))
    inp = INPUT(type=INPUT_MOUSE)
    inp.mi = MOUSEINPUT(nx, ny, ctypes.c_uint32(120 * notches).value, MOVE | WHEEL | ABSOLUTE | VIRTUALDESK, 0, 0)
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def strokes(rect, seconds: float, hz: int = 120):
    """Paint: Lissajous strokes with the left button, ~4 s each, then a short lift.
    Yields (button, points, wheel_notches_per_point)."""
    l, t, r, b = rect
    cx, cy = (l + r) / 2, (t + b) / 2 + (b - t) * 0.05     # a little low: Paint's ribbon is on top
    ax, ay = (r - l) * 0.28, (b - t) * 0.25
    k = 0
    elapsed = 0.0
    while elapsed < seconds:
        n = int(hz * 4.0)
        fa, fb, ph = 1 + k % 3, 2 + (k + 1) % 3, k * 0.7
        pts = []
        for i in range(n):
            s = i / n * 2 * math.pi
            pts.append((round(cx + ax * math.sin(fa * s + ph)), round(cy + ay * math.sin(fb * s))))
        yield "left", pts, 0
        elapsed += 4.0 + 0.4
        k += 1


def orbits(rect, seconds: float, hz: int = 120):
    """Blender: orbit the view with the middle button in slow arcs, in the middle of the 3D viewport.
    Between two arcs the cursor glides (button up) to where the next one starts, as a hand would:
    a jump there read as a stutter in the video. No wheel zoom: each notch is a sudden step, and the
    still cursor while it zoomed read as a freeze (measured on the 27/10 take, 2.1 s still at 16.3 s)."""
    l, t, r, b = rect
    cx, cy = l + (r - l) * 0.38, t + (b - t) * 0.42        # the viewport, left of the side panels
    plan = [(3.0, 520, 60), (2.6, -380, -140), (2.8, 300, 170), (3.2, -560, -40), (2.6, 260, -150),
            (2.8, -200, 180)]
    elapsed = 0.0
    k = 0
    here = (round(cx), round(cy))

    def glide(a, z, dur):
        n = max(2, int(hz * dur))
        return [(round(a[0] + (z[0] - a[0]) * (0.5 - 0.5 * math.cos(math.pi * i / n))),
                 round(a[1] + (z[1] - a[1]) * (0.5 - 0.5 * math.cos(math.pi * i / n)))) for i in range(1, n + 1)]

    while elapsed < seconds:
        dur, dx, dy = plan[k % len(plan)]
        n = int(hz * dur)
        pts = []
        for i in range(n):
            f = 0.5 - 0.5 * math.cos(math.pi * i / n)          # ease in and out, like a hand
            pts.append((round(cx - dx / 2 + dx * f), round(cy - dy / 2 + dy * f + 25 * math.sin(math.pi * f))))
        yield None, [here] + glide(here, pts[0], 0.35), 0
        yield "middle", pts, 0
        here = pts[-1]
        elapsed += dur + 0.35 + 0.1
        k += 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=32)
    ap.add_argument("--log", default="")
    ap.add_argument("--t0-file", default="", help="shared start time (time.time()) written by run_demo.py")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--hz", type=int, default=120)
    ap.add_argument("--app", choices=("paint", "blender"), default="paint")
    a = ap.parse_args()

    rect = primary_rect()
    gestures = strokes if a.app == "paint" else orbits
    title_has = "Paint" if a.app == "paint" else "Blender"
    if a.dry_run:
        for i, (_, pts, _) in enumerate(gestures(rect, a.seconds, a.hz)):
            xs, ys = [p[0] for p in pts], [p[1] for p in pts]
            print(f"stroke {i}: {len(pts)} points, x {min(xs)}..{max(xs)}, y {min(ys)}..{max(ys)}")
        print(f"primary {rect}, virtual desk {(VX, VY, VW, VH)}")
        return 0

    t0 = float(Path(a.t0_file).read_text()) if a.t0_file else time.time()
    log = open(a.log, "w", encoding="utf-8") if a.log else None
    step = 1.0 / a.hz
    last_log = 0.0
    held = False
    expected = None

    def sample(force: bool = False):
        nonlocal last_log
        now = time.time()
        if log and (force or now - last_log >= 0.1):
            title = foreground_title()
            ok = title_has in title
            log.write(json.dumps({"t": round(now - t0, 3), "fg_title": title,
                                  "fg_ok": ok, "fg_is_paint": ok}) + "\n")
            last_log = now

    press = {"left": (LEFTDOWN, LEFTUP), "middle": (MIDDLEDOWN, MIDDLEUP)}
    button = None

    def release():
        if held and expected and button:
            _send(MOVE | press[button][1], *expected)

    def abort(why: str) -> int:
        release()
        print(f"stopped: {why}", file=sys.stderr)
        if log:
            log.close()
        return 2

    # The user's own click: put the program in front, as a person would. In Blender, on the
    # title bar: a click in the viewport would change the selection, and a middle click
    # doesn't activate the window.
    first = next(gestures(rect, 1, a.hz))[1][0]
    if a.app == "blender":
        first = ((rect[0] + rect[2]) // 2, rect[1] + 12)
    move(*first)
    time.sleep(0.2)
    _send(MOVE | LEFTDOWN, *first)
    _send(MOVE | LEFTUP, *first)
    time.sleep(0.4)
    sample(force=True)

    started = time.time()
    longest_gap, last_tick = 0.0, time.time()
    for button, pts, wh in gestures(rect, a.seconds * 3, a.hz):  # the clock, not the plan, ends the take
        if time.time() - started > a.seconds:
            break
        move(*pts[0])
        expected = pts[0]
        time.sleep(0.05)
        if button:
            _send(MOVE | press[button][0], *pts[0])
            held = True
        for i, p in enumerate(pts[1:]):
            if user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000:
                return abort("Esc")
            cx_, cy_ = cursor()
            if expected and abs(cx_ - expected[0]) + abs(cy_ - expected[1]) > 40:
                return abort(f"the mouse moved by someone else (expected {expected}, got {(cx_, cy_)})")
            move(*p)
            if wh and i % wh[0] == 0:
                wheel(*p, wh[1])
            expected = p
            sample()
            now = time.time()
            if now - last_tick > longest_gap:
                longest_gap, gap_at = now - last_tick, now - t0
            last_tick = now
            time.sleep(step)
        release()
        held = False
        for _ in range(4 if a.app == "paint" else 1):  # Paint lifts the pen; in Blender the hand keeps moving
            time.sleep(0.1)
            sample()
    sample(force=True)
    if log:
        log.close()
    if longest_gap > 0.25:  # a stall here is a freeze in the video: say where
        print(f"stall: {longest_gap:.2f} s without moving, at {gap_at:.1f} s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
