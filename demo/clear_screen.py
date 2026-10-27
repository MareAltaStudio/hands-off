"""Clear both monitors before the take: minimise every window (and remember which), so only
the demo shows. `--close-exe PureRef.exe` closes that program's windows instead (always-on-top
boards would cover the take). `--restore` puts the minimised windows back.

    python clear_screen.py --close-exe PureRef.exe
    python clear_screen.py --restore
"""

from __future__ import annotations

import argparse
import ctypes
import json
import time
from ctypes import wintypes
from pathlib import Path

import win32con
import win32gui
import win32process

user32 = ctypes.windll.user32
STATE = Path(__file__).resolve().parent / "out" / "minimized.json"
SKIP_CLASSES = {"Shell_TrayWnd", "Shell_SecondaryTrayWnd", "Progman", "WorkerW"}


def exe_of(h: int) -> str:
    try:
        _, pid = win32process.GetWindowThreadProcessId(h)
        k = ctypes.windll.kernel32.OpenProcess(0x1000, False, pid)
        buf = ctypes.create_unicode_buffer(260)
        n = wintypes.DWORD(260)
        ctypes.windll.kernel32.QueryFullProcessImageNameW(k, 0, buf, ctypes.byref(n))
        ctypes.windll.kernel32.CloseHandle(k)
        return Path(buf.value).name
    except Exception:  # noqa: BLE001
        return ""


def windows() -> list[int]:
    out = []

    def cb(h, _):
        if not win32gui.IsWindowVisible(h) or win32gui.GetClassName(h) in SKIP_CLASSES:
            return True
        if win32gui.GetWindow(h, win32con.GW_OWNER):
            return True
        ex = win32gui.GetWindowLong(h, win32con.GWL_EXSTYLE)
        if ex & win32con.WS_EX_TOOLWINDOW and not ex & win32con.WS_EX_APPWINDOW:
            return True
        if not win32gui.GetWindowText(h):
            return True
        out.append(h)
        return True
    win32gui.EnumWindows(cb, None)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--close-exe", action="append", default=[])
    ap.add_argument("--keep", action="append", default=[], help="title fragment to leave alone")
    ap.add_argument("--restore", action="store_true")
    a = ap.parse_args()

    if a.restore:
        for h in json.loads(STATE.read_text()) if STATE.exists() else []:
            if win32gui.IsWindow(h):
                user32.ShowWindow(h, win32con.SW_SHOWNOACTIVATE)
        print("restored")
        return 0

    close = {e.lower() for e in a.close_exe}
    done, closed = [], []
    for h in windows():
        title = win32gui.GetWindowText(h)
        if any(k.lower() in title.lower() for k in a.keep):
            continue
        exe = exe_of(h).lower()
        if exe in close:
            win32gui.PostMessage(h, win32con.WM_CLOSE, 0, 0)
            closed.append(f"{exe} {title[:50]}")
            continue
        if not user32.IsIconic(h):
            user32.ShowWindow(h, win32con.SW_MINIMIZE)
            done.append(h)
    time.sleep(1.5)
    left = [f"{exe_of(h)} {win32gui.GetWindowText(h)[:50]}" for h in windows()
            if not user32.IsIconic(h) and not any(k.lower() in win32gui.GetWindowText(h).lower() for k in a.keep)]
    STATE.parent.mkdir(exist_ok=True)
    STATE.write_text(json.dumps(done))
    print(f"minimised {len(done)}, closed {len(closed)}: {closed}")
    print(f"still showing: {left}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
