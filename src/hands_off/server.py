"""hands-off - an MCP server that drives Windows programs without your mouse.

Why it exists: an agent that clicks things by synthetic input (SendInput,
pyautogui, AutoHotkey) moves THE cursor and steals THE foreground window -
Windows has one of each per session - so the person at the PC has to stop
working while the agent works. Nothing in this file ever calls SendInput,
moves the cursor or focuses a window on purpose. It works in layers, and
every result says which layer did the work:

    1. UI Automation patterns (Invoke, Toggle, Value, ExpandCollapse,
       SelectionItem, LegacyIAccessible) - by name, on a covered window.
    2. Window messages (BM_CLICK, WM_SETTEXT, WM_COMMAND for classic menus,
       WM_LBUTTONDOWN/UP and WM_CHAR posted to the hwnd) - no cursor.
    3. Nothing else. A program that only reads the real mouse (a game, the
       Photoshop canvas, the Blender viewport) is answered with "use the
       program's own API" - never with a quiet SendInput.

Capture is PrintWindow with PW_RENDERFULLCONTENT (it takes covered windows,
GPU-rendered ones included; calling PrintWindow without that flag is what
gives the familiar black picture), with Windows Graphics Capture as the
fallback when the picture still comes back black.

All UIA work runs on ONE worker thread with COM initialised MTA: UIA calls
from random pool threads are how a COM server ends up wedged. Invoke runs on a
throwaway thread with a timeout, because a Win32 button that opens a modal
dialog does not return from Invoke until the dialog closes.

After every acting tool the foreground window is compared with what it was
before; if the target program grabbed the focus, it is given back and the
result says so. Every acting call is one line in the action log
(HANDS_OFF_LOG, default %LOCALAPPDATA%\\hands-off\\actions.log).

Failures come back as text, never as exceptions: the agent reads them.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as W
import datetime
import io
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutTimeout
from pathlib import Path

# Physical pixels everywhere: UIA rectangles, window rects and the captured
# image must agree, or a click computed from one lands somewhere else.
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:  # noqa: BLE001
    pass

sys.coinit_flags = 0  # COINIT_MULTITHREADED - read by comtypes on import

import win32api  # noqa: E402
import win32con  # noqa: E402
import win32gui  # noqa: E402
import win32process  # noqa: E402

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

LOG = Path(os.environ.get("HANDS_OFF_LOG")
           or Path(os.environ.get("LOCALAPPDATA", Path.home())) / "hands-off" / "actions.log")
TIMEOUT = 30.0       # one tool call, worst case
INVOKE_WAIT = 4.0    # after this, an Invoke is "pending" (modal dialog), not failed
WS_EX_NOACTIVATE = 0x08000000
TCM_GETCURSEL, TCM_SETCURFOCUS = 0x130B, 0x1330
MAX_NODES = 4000     # tree walk ceiling - Chrome/Electron trees are enormous

PW_RENDERFULLCONTENT = 2
SMTO_ABORTIFHUNG = 0x0002


# --------------------------------------------------------------------------
# The single UIA thread.
# --------------------------------------------------------------------------

def _com_init() -> None:
    import comtypes

    comtypes.CoInitializeEx(0)


_worker = ThreadPoolExecutor(max_workers=1, initializer=_com_init,
                             thread_name_prefix="hands-off-uia")
_auto = None


def _uia():
    global _auto
    if _auto is None:
        import uiautomation as auto

        auto.SetGlobalSearchTimeout(1)
        _auto = auto
    return _auto


def _on_worker(fn, *args, timeout: float = TIMEOUT):
    fut = _worker.submit(fn, *args)
    try:
        return fut.result(timeout=timeout)
    except FutTimeout:
        return (f"[error] took longer than {timeout:.0f}s. The program may be hung "
                f"or waiting on a dialog; the next calls may queue behind this one.")
    except Exception as exc:  # noqa: BLE001
        return f"[error] {type(exc).__name__}: {exc}"


# --------------------------------------------------------------------------
# Windows: finding them, the focus guard, the log.
# --------------------------------------------------------------------------

def _proc_name(pid: int) -> str:
    try:
        h = win32api.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
        try:
            return os.path.basename(win32process.GetModuleFileNameEx(h, 0))
        finally:
            win32api.CloseHandle(h)
    except Exception:  # noqa: BLE001
        return "?"


def _top_windows() -> list[dict]:
    out: list[dict] = []

    def cb(h, _):
        if not win32gui.IsWindowVisible(h):
            return True
        title = win32gui.GetWindowText(h)
        if not title:
            return True
        # Cloaked = a UWP/virtual-desktop ghost that is "visible" but not on screen.
        cloaked = ctypes.c_int(0)
        ctypes.windll.dwmapi.DwmGetWindowAttribute(W.HWND(h), 14, ctypes.byref(cloaked), 4)
        if cloaked.value:
            return True
        _, pid = win32process.GetWindowThreadProcessId(h)
        out.append({"hwnd": h, "title": title, "class": win32gui.GetClassName(h),
                    "pid": pid, "exe": _proc_name(pid),
                    "rect": win32gui.GetWindowRect(h),
                    "min": bool(win32gui.IsIconic(h))})
        return True

    win32gui.EnumWindows(cb, None)
    return out


def _resolve(window) -> int | str:
    """hwnd (a number), 'exe:name.exe', or part of the title. Returns the hwnd or an error."""
    s = str(window).strip()
    if s.isdigit():
        h = int(s)
        return h if win32gui.IsWindow(h) else f"[error] there is no window {h}."
    wins = _top_windows()
    if s.lower().startswith("exe:"):
        want = s[4:].strip().lower()
        hits = [w for w in wins if w["exe"].lower() in (want, want + ".exe")]
    else:
        hits = [w for w in wins if w["title"].lower() == s.lower()] or \
               [w for w in wins if s.lower() in w["title"].lower()]
    if not hits:
        return f"[error] no window matches {s!r}. Call list_windows() to see them."
    if len(hits) > 1:
        lst = "\n".join(f"  {w['hwnd']}  {w['exe']}  {w['title'][:70]}" for w in hits[:12])
        return f"[error] {len(hits)} windows match {s!r}; pass the number:\n{lst}"
    return hits[0]["hwnd"]


def _pid_of(h: int) -> int:
    pid = W.DWORD()
    user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
    return pid.value


def _give_focus_back(prev: int) -> bool:
    """The program grabbed the foreground; hand it back to what the user was using.

    Measured with the WinUI Notepad: the steal lasts ~0.2 s and the foreground
    passes through NULL on the way back, so the answer is read after a short
    wait, not on the next line.
    """
    if not prev or not user32.IsWindow(prev):
        return True
    t_me = kernel32.GetCurrentThreadId()
    for _ in range(12):  # retry, don't wait: a refused SetForegroundWindow stays refused
        now = user32.GetForegroundWindow()
        if now == prev:
            return True
        t_now = user32.GetWindowThreadProcessId(now, None) if now else 0
        if t_now:
            user32.AttachThreadInput(t_me, t_now, True)
        try:
            user32.SetForegroundWindow(prev)
            if user32.GetForegroundWindow() != prev:
                # The foreground lock refuses SetForegroundWindow now and then
                # while a freshly launched app is still activating (~1 launch
                # in 7 of Calculator); SwitchToThisWindow is not subject to it.
                user32.SwitchToThisWindow(prev, True)
        finally:
            if t_now:
                user32.AttachThreadInput(t_me, t_now, False)
        for _ in range(3):
            if user32.GetForegroundWindow() == prev:
                return True
            time.sleep(0.01)
    return False


def _guard_focus(prev: int, target_pids: set[int], watch_s: float = 0.9) -> str:
    """Watch the foreground for a moment after an action. Only a steal by the
    TARGET program is undone - if the user switched windows themselves, their
    choice stands."""
    stolen = False
    end = time.time() + watch_s
    while time.time() < end:
        now = user32.GetForegroundWindow()
        if now and now != prev and _pid_of(now) in target_pids:
            stolen = True
            _give_focus_back(prev)
        time.sleep(0.02)
    if not stolen:
        return ""
    # Judge by where the focus ended, not by the first attempt that lost a
    # race; an app still activating can refuse for a while, so keep trying.
    deadline = time.time() + 2.0
    while time.time() < deadline:
        now = user32.GetForegroundWindow()
        if not (now and now != prev and _pid_of(now) in target_pids):
            break
        if _give_focus_back(prev):
            break
        time.sleep(0.1)
    now = user32.GetForegroundWindow()
    if now and now != prev and _pid_of(now) in target_pids:
        now = user32.GetForegroundWindow()
        who = f"{win32gui.GetWindowText(now)[:50]!r} ({win32gui.GetClassName(now)})" if now else "nobody"
        return f"the program stole the focus and I could NOT give it back; focus is now on {who} - tell the user"
    return "the program took the focus for a moment; given back"


def _no_activate(h: int):
    """Mark the target's top-level window WS_EX_NOACTIVATE for the duration of
    an action, so the activation that a UIA call can trigger has nowhere to go.
    Returns the old style to restore, or None if nothing was changed."""
    if os.environ.get("HANDS_OFF_NOACTIVATE", "1") == "0":
        return None
    top = user32.GetAncestor(h, 2) or h  # GA_ROOT
    old = user32.GetWindowLongW(top, win32con.GWL_EXSTYLE)
    if old & WS_EX_NOACTIVATE:
        return None
    user32.SetWindowLongW(top, win32con.GWL_EXSTYLE, old | WS_EX_NOACTIVATE)
    return top, old


def _acting(name: str, h: int, fn) -> str:
    """Run an acting tool on the worker with the focus guard and the log."""
    fg = user32.GetForegroundWindow()
    pids = {_pid_of(h)}
    mark = _no_activate(h) if pids != {_pid_of(fg)} else None
    try:
        out = _on_worker(fn)
    finally:
        if mark:
            user32.SetWindowLongW(mark[0], win32con.GWL_EXSTYLE, mark[1])
    if pids != {_pid_of(fg)}:  # if the user is IN that program, there is nothing to guard
        g = _guard_focus(fg, pids)
        if g:
            out = f"{out}\n[guard] {g}"
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            stamp = datetime.datetime.now().isoformat(timespec="seconds")
            first = str(out).splitlines()[0] if out else ""
            f.write(f"{stamp}\t{name}\t{h}\t{first}\n")
    except Exception:  # noqa: BLE001 - the log never costs the action
        pass
    return out


# --------------------------------------------------------------------------
# UIA tree: walking, paths, finding a target.
# --------------------------------------------------------------------------

_PATTERNS = [  # (short name, IsXPatternAvailable property id)
    ("invoke", 30031), ("toggle", 30041), ("value", 30043), ("expand", 30028),
    ("select", 30036), ("text", 30040), ("range", 30033), ("scroll", 30034),
]


def _patterns(c) -> list[str]:
    got = []
    for short, pid in _PATTERNS:
        try:
            if c.Element.GetCurrentPropertyValue(pid):
                got.append(short)
        except Exception:  # noqa: BLE001
            pass
    return got


def _root(hwnd: int):
    return _uia().ControlFromHandle(hwnd)


def _children(c) -> list:
    try:
        return c.GetChildren()
    except Exception:  # noqa: BLE001
        return []


def _walk(root, depth: int, cap: int = MAX_NODES):
    """Depth-first (path, depth, control), so the listing reads as a tree.
    Paths are child indices: '2.0.5'."""
    stack = [("", 0, root)]
    seen = 0
    while stack and seen < cap:
        path, d, c = stack.pop()
        seen += 1
        yield path, d, c
        if d < depth:
            kids = _children(c)
            for i in range(len(kids) - 1, -1, -1):
                stack.append((f"{path}.{i}" if path else str(i), d + 1, kids[i]))


def _by_path(root, path: str):
    c = root
    for part in [p for p in path.split(".") if p != ""]:
        kids = _children(c)
        i = int(part)
        if i >= len(kids):
            return None
        c = kids[i]
    return c


def _rect(c) -> tuple[int, int, int, int] | None:
    try:
        r = c.BoundingRectangle
        if r.right > r.left and r.bottom > r.top:
            return r.left, r.top, r.right, r.bottom
    except Exception:  # noqa: BLE001
        pass
    return None


def _line(path: str, c, indent: int) -> str:
    name = (c.Name or "").replace("\n", " ")[:60]
    aid = c.AutomationId or ""
    bits = [f"#{path or '.'}", c.ControlTypeName.replace("Control", "")]
    if name:
        bits.append(repr(name))
    if aid and aid != name:
        bits.append(f"id={aid[:40]}")
    pats = _patterns(c)
    if pats:
        bits.append("(" + ",".join(pats) + ")")
    try:
        if not c.IsEnabled:
            bits.append("[disabled]")
        if c.IsOffscreen:
            bits.append("[offscreen]")
    except Exception:  # noqa: BLE001
        pass
    return "  " * indent + " ".join(bits)


def _find(root, target: str):
    """'#2.0.5' | 'Type:Name' | 'Name' | 'id=AutomationId'. Returns (path, ctrl, note)."""
    target = target.strip()
    if target.startswith("#"):
        p = target[1:].strip(".")
        c = _by_path(root, p)
        return (p, c, "") if c is not None else (None, None, f"path {target} no longer exists")
    kind = None
    want = target
    if target.lower().startswith("id="):
        want_id = target[3:].strip()
        for path, _, c in _walk(root, 60):
            if (c.AutomationId or "") == want_id:
                return path, c, ""
        return None, None, f"no element with id={want_id!r}"
    m = re.match(r"^([A-Za-z]+):(.*)$", target)
    if m:
        kind, want = m.group(1).lower(), m.group(2).strip()
    w = want.casefold()
    exact, part = [], []
    for path, _, c in _walk(root, 60):
        tname = c.ControlTypeName.replace("Control", "").lower()
        if kind and tname != kind:
            continue
        name = (c.Name or "").casefold()
        if name == w or (c.AutomationId or "").casefold() == w:
            exact.append((path, c))
        elif w and w in name:
            part.append((path, c))
    hits = exact or part
    if not hits:
        return None, None, f"nothing matches {target!r}; see tree()"

    def usable(pc):
        try:
            return pc[1].IsEnabled and not pc[1].IsOffscreen
        except Exception:  # noqa: BLE001
            return False

    hits.sort(key=lambda pc: not usable(pc))
    note = f"{len(hits)} candidates, used the first" if len(hits) > 1 else ""
    return hits[0][0], hits[0][1], note


def _describe(path, c) -> str:
    return f"#{path} {c.ControlTypeName.replace('Control', '')} {(c.Name or '')[:50]!r}"


# --------------------------------------------------------------------------
# Window messages (the no-cursor fallback).
# --------------------------------------------------------------------------

# Child windows that only show pixels: input posted to them is dropped. Chrome,
# Edge and Electron draw the page into "Intermediate D3D Window" but read the
# mouse on the Chrome_WidgetWin_* above it (measured: the click posted to the
# D3D child never reached the page; the same click posted one level up arrived
# as a click with isTrusted = true).
_OUTPUT_ONLY = ("Intermediate D3D Window",)


def _deepest_child(top: int, sx: int, sy: int) -> int:
    h = top
    while True:
        pt = W.POINT(sx, sy)
        user32.ScreenToClient(h, ctypes.byref(pt))
        ch = user32.RealChildWindowFromPoint(h, pt)
        if not ch or ch == h or win32gui.GetClassName(ch) in _OUTPUT_ONLY:
            return h
        h = ch


def _post_click(top: int, sx: int, sy: int, button: str = "left", double: bool = False) -> str:
    h = _deepest_child(top, sx, sy)
    pt = W.POINT(sx, sy)
    user32.ScreenToClient(h, ctypes.byref(pt))
    lp = win32api.MAKELONG(pt.x & 0xFFFF, pt.y & 0xFFFF)
    down, up, mk = {
        "left": (win32con.WM_LBUTTONDOWN, win32con.WM_LBUTTONUP, win32con.MK_LBUTTON),
        "right": (win32con.WM_RBUTTONDOWN, win32con.WM_RBUTTONUP, win32con.MK_RBUTTON),
        "middle": (win32con.WM_MBUTTONDOWN, win32con.WM_MBUTTONUP, win32con.MK_MBUTTON),
    }[button]
    user32.PostMessageW(h, win32con.WM_MOUSEMOVE, 0, lp)
    for n in range(2 if double else 1):
        user32.PostMessageW(h, down, mk, lp)
        user32.PostMessageW(h, up, 0, lp)
        if double and n == 0:
            user32.PostMessageW(h, win32con.WM_LBUTTONDBLCLK, mk, lp)
    return f"click message to hwnd {h} ({win32gui.GetClassName(h)}) at {pt.x},{pt.y}"


def _focus_hwnd(top: int) -> int:
    """The control that has keyboard focus inside `top`'s thread, without focusing anything."""
    tid = user32.GetWindowThreadProcessId(top, None)

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [("cbSize", W.DWORD), ("flags", W.DWORD), ("hwndActive", W.HWND),
                    ("hwndFocus", W.HWND), ("hwndCapture", W.HWND), ("hwndMenuOwner", W.HWND),
                    ("hwndMoveSize", W.HWND), ("hwndCaret", W.HWND), ("rcCaret", W.RECT)]

    gi = GUITHREADINFO(cbSize=ctypes.sizeof(GUITHREADINFO))
    if user32.GetGUIThreadInfo(tid, ctypes.byref(gi)) and gi.hwndFocus:
        return gi.hwndFocus
    return top


_VK = {"enter": 0x0D, "tab": 0x09, "esc": 0x1B, "space": 0x20,
       "backspace": 0x08, "delete": 0x2E, "del": 0x2E, "up": 0x26, "down": 0x28,
       "left": 0x25, "right": 0x27, "home": 0x24, "end": 0x23, "pgup": 0x21, "pgdn": 0x22,
       "pageup": 0x21, "pagedown": 0x22, "insert": 0x2D, "ins": 0x2D,
       "ctrl": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B,
       **{f"f{i}": 0x6F + i for i in range(1, 13)}}


def _post_keys(h: int, combo: str) -> None:
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    vks = []
    for p in parts:
        if p in _VK:
            vks.append(_VK[p])
        elif len(p) == 1:
            vks.append(user32.VkKeyScanW(ord(p)) & 0xFF)
        else:
            raise ValueError(f"unknown key {p!r}")
    alt = 0x12 in vks
    kd, ku = (win32con.WM_SYSKEYDOWN, win32con.WM_SYSKEYUP) if alt else (win32con.WM_KEYDOWN, win32con.WM_KEYUP)
    for vk in vks:
        sc = user32.MapVirtualKeyW(vk, 0)
        user32.PostMessageW(h, kd, vk, 1 | (sc << 16) | ((1 << 29) if alt else 0))
    for vk in reversed(vks):
        sc = user32.MapVirtualKeyW(vk, 0)
        user32.PostMessageW(h, ku, vk, 1 | (sc << 16) | (3 << 30) | ((1 << 29) if alt else 0))


def _post_text(h: int, text: str) -> None:
    for ch in text:
        if ch == "\n":
            _post_keys(h, "enter")
        else:
            user32.PostMessageW(h, win32con.WM_CHAR, ord(ch), 1)


# --------------------------------------------------------------------------
# Capture.
# --------------------------------------------------------------------------

def _printwindow(h: int):
    import win32ui
    from PIL import Image

    l, t, r, b = win32gui.GetWindowRect(h)
    w, hh = r - l, b - t
    hdc = win32gui.GetWindowDC(h)
    dc = win32ui.CreateDCFromHandle(hdc)
    mdc = dc.CreateCompatibleDC()
    bmp = win32ui.CreateBitmap()
    bmp.CreateCompatibleBitmap(dc, w, hh)
    mdc.SelectObject(bmp)
    try:
        user32.PrintWindow(h, mdc.GetSafeHdc(), PW_RENDERFULLCONTENT)
        info = bmp.GetInfo()
        return Image.frombuffer("RGB", (info["bmWidth"], info["bmHeight"]),
                                bmp.GetBitmapBits(True), "raw", "BGRX", 0, 1).copy()
    finally:
        win32gui.DeleteObject(bmp.GetHandle())
        mdc.DeleteDC()
        dc.DeleteDC()
        win32gui.ReleaseDC(h, hdc)


def _wgc(h: int):
    from PIL import Image
    from windows_capture import WindowsCapture

    done, res = threading.Event(), {}
    cap = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=h)

    @cap.event
    def on_frame_arrived(frame, control):
        buf = frame.frame_buffer  # BGRA
        res["img"] = Image.fromarray(buf[:, :, [2, 1, 0]].copy())
        control.stop()
        done.set()

    @cap.event
    def on_closed():
        done.set()

    cap.start_free_threaded()
    done.wait(5)
    return res.get("img")


def _grab(h: int):
    img = _printwindow(h)
    how = "PrintWindow"
    if img.convert("L").getextrema()[1] < 8:
        alt = _wgc(h)
        if alt is not None:
            img, how = alt, "WGC"
    return img, how


def _mcp_image(data: bytes):
    try:
        from mcp.server.mcpserver.utilities.types import Image  # mcp >= 2
    except ImportError:
        from mcp.server.fastmcp.utilities.types import Image
    return Image(data=data, format="png")


# --------------------------------------------------------------------------
# Tools - read-only.
# --------------------------------------------------------------------------

def list_windows(filter: str = "") -> str:  # noqa: A002 - the tool's public parameter name
    """List open windows (number, program, monitor, minimised, title).
    `filter` matches part of the title or the .exe. This is the first step:
    every other tool takes the number, 'exe:name.exe' or part of the title."""
    f = filter.lower()
    mons = [(win32api.GetMonitorInfo(m[0])["Monitor"], m[0]) for m in win32api.EnumDisplayMonitors()]
    rows = []
    for w in _top_windows():
        if f and f not in w["title"].lower() and f not in w["exe"].lower():
            continue
        cx, cy = (w["rect"][0] + w["rect"][2]) // 2, (w["rect"][1] + w["rect"][3]) // 2
        mon = next((i + 1 for i, (r, _) in enumerate(mons)
                    if r[0] <= cx < r[2] and r[1] <= cy < r[3]), "?")
        rows.append(f"{w['hwnd']:>9}  {w['exe'][:22]:22}  m{mon}  "
                    f"{'[min] ' if w['min'] else ''}{w['title'][:80]}")
    return "\n".join(rows) or "no windows."


def tree(window: str, depth: int = 6, filter: str = "", max_lines: int = 250) -> str:  # noqa: A002
    """Show a window's controls through UI Automation: #path, type, name, id
    and what can be done with it (invoke, toggle, value, expand, select...).
    Works on a covered window. `filter` shows only the lines containing the
    text (but walks everything). Programs that draw their own interface (games,
    the Photoshop canvas, Blender) come back almost empty here: for those, use
    capture() + click_xy() or the program's own API."""
    h = _resolve(window)
    if isinstance(h, str):
        return h

    def work():
        root = _root(h)
        f = filter.casefold()
        out, n = [], 0
        for path, d, c in _walk(root, max(0, int(depth))):
            n += 1
            ln = _line(path, c, d)
            if f and f not in ln.casefold():
                continue
            out.append(ln)
            if len(out) >= max_lines:
                out.append(f"... (stopped at {max_lines} lines; use filter or less depth)")
                break
        head = f"window {h}: {n} elements walked"
        if n <= 3:
            head += (" - almost nothing through UIA: this program draws its own interface. "
                     "Use capture()/click_xy() or its API.")
        return head + "\n" + "\n".join(out)

    return _on_worker(work)


def read(window: str, target: str) -> str:
    """Read one control: name, value/text, state (checked, expanded, enabled)
    and rectangle. `target` = '#path' (from tree), 'Type:Name', 'Name' or
    'id=AutomationId'."""
    h = _resolve(window)
    if isinstance(h, str):
        return h

    def work():
        path, c, note = _find(_root(h), target)
        if c is None:
            return f"[error] {note}"
        out = [_describe(path, c)]
        for getter, label, attr in (("GetValuePattern", "value", "Value"),
                                    ("GetTogglePattern", "checked", "ToggleState"),
                                    ("GetExpandCollapsePattern", "expanded", "ExpandCollapseState"),
                                    ("GetSelectionItemPattern", "selected", "IsSelected"),
                                    ("GetRangeValuePattern", "value", "Value")):
            try:
                p = getattr(c, getter)()
                if p:
                    out.append(f"{label}: {getattr(p, attr)}")
            except Exception:  # noqa: BLE001
                pass
        try:
            tp = c.GetTextPattern()
            if tp:
                out.append(f"text: {tp.DocumentRange.GetText(4000)!r}")
        except Exception:  # noqa: BLE001
            pass
        out.append(f"rect: {_rect(c)}")
        try:
            out.append(f"enabled: {c.IsEnabled}")
        except Exception:  # noqa: BLE001
            pass
        return "\n".join(out) + (f"\n({note})" if note else "")

    return _on_worker(work)


def capture(window: str, target: str = "", max_width: int = 1600):
    """Take a picture of the window even when other windows cover it. With
    `target`, crop to that control. Returns the image and its scale:
    click_xy coordinates are pixels of the whole window, so divide the image
    pixel by the scale. A minimised window can't be captured: call move() first."""
    h = _resolve(window)
    if isinstance(h, str):
        return h
    if win32gui.IsIconic(h):
        return "[error] the window is minimised; move(window, monitor) restores it without focus."

    def crop_rect():
        path, c, note = _find(_root(h), target)
        return _rect(c) if c is not None else note

    try:
        img, how = _grab(h)
    except Exception as exc:  # noqa: BLE001
        return f"[error] capture: {exc!r}"
    ox, oy = 0, 0
    if target:
        r = _on_worker(crop_rect)
        if isinstance(r, str) or r is None:
            return f"[error] {r}"
        wl, wt, _, _ = win32gui.GetWindowRect(h)
        ox, oy = r[0] - wl, r[1] - wt
        img = img.crop((ox, oy, r[2] - wl, r[3] - wt))
    scale = min(1.0, max_width / max(1, img.width))
    if scale < 1.0:
        img = img.resize((round(img.width * scale), round(img.height * scale)))
    buf = io.BytesIO()
    img.save(buf, "PNG")
    info = (f"window {h} via {how}; scale {scale:.3f}"
            + (f"; crop starts at {ox},{oy} of the window" if target else "")
            + f". For click_xy: x = {ox} + px/scale, y = {oy} + py/scale.")
    return [info, _mcp_image(buf.getvalue())]


# --------------------------------------------------------------------------
# Tools - acting. Each goes through _acting (focus guard + log).
# --------------------------------------------------------------------------

def _invoke_bounded(c) -> str:
    """Invoke on a throwaway thread: a modal dialog keeps Invoke from returning."""
    box = {}

    def run():
        import comtypes

        comtypes.CoInitializeEx(0)
        try:
            c.GetInvokePattern().Invoke(waitTime=0)
            box["ok"] = True
        except Exception as exc:  # noqa: BLE001
            box["err"] = exc

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(INVOKE_WAIT)
    if t.is_alive():
        return "pending"
    if "err" in box:
        raise box["err"]
    return "ok"


def _win32_tab(item) -> str | None:
    """Select a tab of a Win32 tab control (SysTabControl32) by message.
    TCM_SETCURFOCUS, unlike TCM_SETCURSEL, sends the parent the selection
    notifications, so a property sheet really switches its page. Returns
    "ok", or None when the tab isn't a Win32 one (the caller falls back to UIA)."""
    try:
        parent = item.GetParentControl()
        nh = parent.NativeWindowHandle if parent else 0
        if not nh or win32gui.GetClassName(nh) != "SysTabControl32":
            return None
        tabs = [x for x in parent.GetChildren() if x.ControlTypeName == "TabItemControl"]
        index = next(i for i, x in enumerate(tabs) if x.Name == item.Name)
    except Exception:  # noqa: BLE001
        return None
    res = W.DWORD()
    user32.SendMessageTimeoutW(nh, TCM_SETCURFOCUS, index, 0, SMTO_ABORTIFHUNG, 3000, ctypes.byref(res))
    return "ok"


def invoke(window: str, target: str, action: str = "click") -> str:
    """Press a control WITHOUT the mouse: button, menu item, tab, checkbox,
    list item. `target` = '#path' (from tree), 'Type:Name' (e.g.
    'Button:Save'), 'Name' or 'id=AutomationId'. `action`: click (default),
    toggle, select, expand, collapse. Says which layer did the work (UIA or
    window message). The window can be covered or on another monitor."""
    h = _resolve(window)
    if isinstance(h, str):
        return h

    def work():
        path, c, note = _find(_root(h), target)
        if c is None:
            return f"[error] {note}"
        what = _describe(path, c)
        tail = f" ({note})" if note else ""
        a = action.lower()
        nh = c.NativeWindowHandle
        if a in ("toggle", "click") and nh and win32gui.GetClassName(nh).lower() == "button":
            # BM_CLICK presses a Win32 button or checkbox without focusing it
            user32.PostMessageW(nh, win32con.BM_CLICK, 0, 0)
            return f"{'toggled' if a == 'toggle' else 'clicked'} (BM_CLICK message): {what}{tail}"
        if a in ("select", "click") and c.ControlTypeName == "TabItemControl":
            tab = _win32_tab(c)
            if tab:
                return f"selected (TCM_SETCURFOCUS message): {what}{tail}" if tab == "ok" else tab
        try:
            if a == "toggle" and c.GetTogglePattern():
                c.GetTogglePattern().Toggle(waitTime=0)
                return f"toggled (UIA Toggle): {what}{tail}"
            if a == "select" and c.GetSelectionItemPattern():
                c.GetSelectionItemPattern().Select(waitTime=0)
                return f"selected (UIA SelectionItem): {what}{tail}"
            if a in ("expand", "collapse") and c.GetExpandCollapsePattern():
                p = c.GetExpandCollapsePattern()
                (p.Expand if a == "expand" else p.Collapse)(waitTime=0)
                return f"{a}ed (UIA ExpandCollapse): {what}{tail}"
            if a == "click":
                if c.GetInvokePattern():
                    if _invoke_bounded(c) == "pending":
                        return (f"invoked (UIA Invoke), and the program has not answered yet - "
                                f"it probably opened a dialog; see list_windows(): {what}{tail}")
                    return f"clicked (UIA Invoke): {what}{tail}"
                for getter, call, label in (("GetTogglePattern", "Toggle", "Toggle"),
                                            ("GetSelectionItemPattern", "Select", "SelectionItem"),
                                            ("GetExpandCollapsePattern", "Expand", "ExpandCollapse")):
                    p = getattr(c, getter)()
                    if p:
                        getattr(p, call)(waitTime=0)
                        return f"clicked (UIA {label}): {what}{tail}"
                try:
                    lp = c.GetLegacyIAccessiblePattern()
                    if lp and lp.DefaultAction:
                        lp.DoDefaultAction()
                        return f"clicked (MSAA DoDefaultAction '{lp.DefaultAction}'): {what}{tail}"
                except Exception:  # noqa: BLE001
                    pass
        except Exception as exc:  # noqa: BLE001
            return f"[error] {action} on {what}: {exc!r}"
        r = _rect(c)
        if a == "click" and r:
            msg = _post_click(h, (r[0] + r[2]) // 2, (r[1] + r[3]) // 2)
            return f"clicked by {msg} - no UIA pattern; check with capture(): {what}{tail}"
        return f"[error] {what} does not accept '{action}' and has no rectangle to click."

    return _acting("invoke", h, work)


def type_text(window: str, target: str, text: str, enter: bool = False) -> str:
    """Write into a field WITHOUT the keyboard or focus: replaces the field's
    whole value (UIA Value, or WM_SETTEXT on classic edit boxes; as a last
    resort the characters go by message). `target` as in invoke(); empty =
    the control that already has focus inside the window. `enter` presses
    Enter afterwards."""
    h = _resolve(window)
    if isinstance(h, str):
        return h

    def work():
        target_hwnd = None
        what = "the window's focused control"
        if target:
            path, c, note = _find(_root(h), target)
            if c is None:
                return f"[error] {note}"
            what = _describe(path, c)
            nh = c.NativeWindowHandle
            if nh and "edit" in win32gui.GetClassName(nh).lower():
                # A classic edit box takes WM_SETTEXT without being focused; UIA
                # SetValue focuses the control first, which activates its window.
                res = W.DWORD()
                user32.SendMessageTimeoutW(nh, win32con.WM_SETTEXT, 0, ctypes.c_wchar_p(text),
                                           SMTO_ABORTIFHUNG, 3000, ctypes.byref(res))
                if enter:
                    _post_keys(nh, "enter")
                return f"written (WM_SETTEXT{' + Enter' if enter else ''}): {what}"
            try:
                vp = c.GetValuePattern()
                if vp and not vp.IsReadOnly:
                    vp.SetValue(text, waitTime=0)
                    if enter:
                        _post_keys(c.NativeWindowHandle or _focus_hwnd(h), "enter")
                    return f"written (UIA Value{' + Enter by message' if enter else ''}): {what}"
            except Exception:  # noqa: BLE001
                pass
            target_hwnd = c.NativeWindowHandle
        target_hwnd = target_hwnd or _focus_hwnd(h)
        cls = win32gui.GetClassName(target_hwnd).lower()
        if "edit" in cls:
            res = W.DWORD()
            user32.SendMessageTimeoutW(target_hwnd, win32con.WM_SETTEXT, 0, ctypes.c_wchar_p(text),
                                       SMTO_ABORTIFHUNG, 3000, ctypes.byref(res))
            how = "WM_SETTEXT"
        else:
            _post_text(target_hwnd, text)
            how = f"WM_CHAR to {cls}"
        if enter:
            _post_keys(target_hwnd, "enter")
        return f"written ({how}{' + Enter' if enter else ''}): {what}. Check with read()."

    return _acting("type_text", h, work)


def keys(window: str, combo: str, target: str = "") -> str:
    """Send keys to the window by message, without focus: 'enter', 'esc',
    'tab', 'f5', 'ctrl+s', 'alt+f4', 'down'... Without `target`, they go to
    the control that has focus inside the window. WARNING: ctrl/alt shortcuts
    fail in many programs, because they read the real keyboard state - prefer
    menu() or invoke() on the button. Check the effect with capture()/read()."""
    h = _resolve(window)
    if isinstance(h, str):
        return h

    def work():
        th = None
        if target:
            path, c, note = _find(_root(h), target)
            if c is None:
                return f"[error] {note}"
            th = c.NativeWindowHandle
        th = th or _focus_hwnd(h)
        try:
            _post_keys(th, combo)
        except ValueError as exc:
            return f"[error] {exc}"
        return f"keys {combo!r} by message to hwnd {th} ({win32gui.GetClassName(th)})."

    return _acting("keys", h, work)


def click_xy(window: str, x: int, y: int, button: str = "left", double: bool = False) -> str:
    """Click a point in the window WITHOUT moving the cursor (a mouse message
    to the control under the point). x,y in pixels of the whole window (the
    top-left of capture()'s image at scale 1). For controls with no name in
    the tree. Does not work on programs that read the real mouse (games, the
    Photoshop canvas, the Blender viewport) - use the program's API there."""
    h = _resolve(window)
    if isinstance(h, str):
        return h
    if button not in ("left", "right", "middle"):
        return "[error] button = left, right or middle."

    def work():
        l, t, _, _ = win32gui.GetWindowRect(h)
        return "clicked by " + _post_click(h, l + int(x), t + int(y), button, double) + \
            ". A message has no confirmation: check with capture()."

    return _acting("click_xy", h, work)


def _menu_win32(h: int, steps: list[str]) -> str | None:
    hm = win32gui.GetMenu(h)
    if not hm:
        return None

    def clean(s):
        return s.split("\t")[0].replace("&", "").strip().casefold()

    for depth, want in enumerate(steps):
        labels = []
        for i in range(user32.GetMenuItemCount(hm)):
            buf = ctypes.create_unicode_buffer(256)
            user32.GetMenuStringW(hm, i, buf, 256, win32con.MF_BYPOSITION)
            labels.append(buf.value)
        w = want.casefold()
        found = next((i for i, s in enumerate(labels) if clean(s) == w), None)
        if found is None:
            found = next((i for i, s in enumerate(labels) if s and w in clean(s)), None)
        if found is None:
            have = ", ".join(clean(s) for s in labels if s)
            return f"[error] {want!r} is not in the classic menu (level {depth + 1}). There is: {have}"
        if depth == len(steps) - 1:
            cid = user32.GetMenuItemID(hm, found)
            if cid in (-1, 0xFFFFFFFF):
                return f"[error] {want!r} is a submenu, not a command."
            state = user32.GetMenuState(hm, found, win32con.MF_BYPOSITION)
            user32.PostMessageW(h, win32con.WM_COMMAND, cid, 0)
            extra = ""
            if state & win32con.MF_CHECKED:
                # MFC refreshes check marks only when the menu is shown, so the
                # mark may be stale - say "toggle", never which way it went.
                extra = " - an on/off item: only capture() tells its real state"
            if state & (win32con.MF_GRAYED | win32con.MF_DISABLED):
                extra = " - the item was DISABLED in the menu; the program may ignore it"
            return (f"menu {clean(labels[found])!r} (WM_COMMAND {cid} message, nothing opened)"
                    f"{extra}. Check with capture().")
        hm = user32.GetSubMenu(hm, found)
    return None


def menu(window: str, path: str) -> str:
    """Choose a menu item: 'File > Save As'. On classic Windows menus it sends
    the command directly (nothing opens on screen); on modern ones it opens
    and invokes through UIA. Use the labels as the program shows them, in its
    own language."""
    h = _resolve(window)
    if isinstance(h, str):
        return h
    steps = [s.strip() for s in re.split(r">|->|/", path) if s.strip()]
    if not steps:
        return "[error] empty path."

    def work():
        r = _menu_win32(h, steps)
        if r is not None:
            return r
        auto = _uia()
        root = _root(h)
        _, pid = win32process.GetWindowThreadProcessId(h)
        scope = root
        for i, want in enumerate(steps):
            _, c, note = _find(scope, f"MenuItem:{want}")
            if c is None and scope is not root:
                _, c, note = _find(root, f"MenuItem:{want}")
            if c is None:  # popups of classic-in-UIA menus are their own top-level windows
                for pw in auto.GetRootControl().GetChildren():
                    if pw.ProcessId == pid and pw.ControlTypeName in ("MenuControl", "WindowControl") \
                            and pw.NativeWindowHandle != h:
                        _, c, note = _find(pw, f"MenuItem:{want}")
                        if c is not None:
                            break
            if c is None:
                return f"[error] could not find the item {want!r} (step {i + 1}): {note}"
            last = i == len(steps) - 1
            ec = c.GetExpandCollapsePattern()
            if not last and ec:
                ec.Expand(waitTime=0)
                time.sleep(0.35)
                scope = c
                continue
            if c.GetInvokePattern():
                if _invoke_bounded(c) == "pending":
                    return (f"menu {' > '.join(steps)} (UIA Invoke) - it opened something that is "
                            f"still waiting; see list_windows().")
                return f"menu {' > '.join(steps)} (UIA Invoke)"
            if ec:
                ec.Expand(waitTime=0)
                return f"menu {' > '.join(steps)} expanded (UIA)"
            return f"[error] {want!r} cannot be invoked through UIA."
        return "[error] the menu path ended without an action."

    return _acting("menu", h, work)


def _monitor_work_area(n: int):
    mons = [win32api.GetMonitorInfo(m[0]) for m in win32api.EnumDisplayMonitors()]
    prim = [m for m in mons if m["Flags"] & 1]
    rest = [m for m in mons if not m["Flags"] & 1]
    order = prim + rest
    if n < 1 or n > len(order):
        return None
    return order[n - 1]["Work"]


_CORNERS = ("top-left", "top-right", "bottom-left", "bottom-right")


def move(window: str, monitor: int = 2, corner: str = "top-left") -> str:
    """Move the window to a monitor (1 = primary, 2 = the next one...)
    without giving it focus, restoring it if minimised. `corner` = top-left,
    top-right, bottom-left or bottom-right of that monitor. Use it to work off
    the user's screen, or out of the part of it they are looking at."""
    h = _resolve(window)
    if isinstance(h, str):
        return h
    if corner not in _CORNERS:
        return f"[error] corner = {', '.join(_CORNERS)}."

    def work():
        wa = _monitor_work_area(int(monitor))
        if wa is None:
            return f"[error] there is no monitor {monitor}."
        if win32gui.IsIconic(h):
            user32.ShowWindow(h, win32con.SW_SHOWNOACTIVATE)
        user32.ShowWindow(h, win32con.SW_SHOWNOACTIVATE)  # out of maximised, so it can move
        l, t, r, b = win32gui.GetWindowRect(h)
        w = min(r - l, wa[2] - wa[0])
        hh = min(b - t, wa[3] - wa[1])
        x = wa[2] - w - 20 if corner.endswith("right") else wa[0] + 20
        y = wa[3] - hh - 20 if corner.startswith("bottom") else wa[1] + 20
        user32.SetWindowPos(h, 0, x, y, w, hh,
                            win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER)
        return f"window {h} on monitor {monitor} at {win32gui.GetWindowRect(h)}"

    return _acting("move", h, work)


def launch(command: str, arguments: str = "", monitor: int = 0, corner: str = "top-left",
           wait_s: float = 15.0) -> str:
    """Start a program (or open a file) without stealing focus. Returns the
    new window's number. `command` = exe or path; `arguments` as on the
    command line. `monitor` > 0 moves the new window there (e.g. 2, to keep
    it off the user's screen), at `corner` as in move(). If the program grabs
    the focus while opening, the guard gives it back."""
    command, arguments = os.path.expandvars(command), os.path.expandvars(arguments)  # %LOCALAPPDATA% etc.
    before = {w["hwnd"] for w in _top_windows()}
    fg = user32.GetForegroundWindow()
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 4  # SW_SHOWNOACTIVATE
    try:
        if os.path.isfile(command) and not command.lower().endswith((".exe", ".bat", ".cmd")):
            os.startfile(command)  # a document: let its program open it
            pid = None
        else:
            line = f'"{command}" {arguments}'.strip() if " " in command else f"{command} {arguments}".strip()
            pid = subprocess.Popen(line, startupinfo=si, cwd=os.path.dirname(command) or None).pid
    except OSError as exc:
        if getattr(exc, "winerror", None) == 740:
            return (f"[error] {command!r} needs administrator rights (UAC). hands-off never clicks the UAC "
                    "prompt: start it from an elevated shell, or ask the user.")
        return f"[error] could not start {command!r}: {exc!r}"
    except Exception as exc:  # noqa: BLE001
        return f"[error] could not start {command!r}: {exc!r}"
    deadline = time.time() + float(wait_s)
    new = None
    while time.time() < deadline and new is None:
        time.sleep(0.3)
        fresh = [w for w in _top_windows() if w["hwnd"] not in before]
        if fresh:
            own = [w for w in fresh if pid and w["pid"] == pid]
            new = (own or fresh)[0]
    # A program that opens takes the foreground late and sometimes twice (a
    # UWP app through ApplicationFrameHost), so watch for a while instead of
    # checking once - a single check right after the window appeared lost
    # the race when the server ran under an MCP client.
    pids = {p for p in (pid, new and new["pid"]) if p}
    g = _guard_focus(fg, pids, watch_s=1.5) if pids else ""
    note = f"; {g}" if g else ""
    if new is None:
        return f"started (pid {pid}), but no new window within {wait_s:.0f}s{note}."
    moved = ("\n" + move(str(new["hwnd"]), monitor, corner)) if monitor else ""
    return f"window {new['hwnd']} {new['exe']} {new['title'][:60]!r}{note}{moved}"


def close(window: str) -> str:
    """Ask the window to close (same as its X button). If something is
    unsaved, the program asks - answer the dialog with tree()/invoke()."""
    h = _resolve(window)
    if isinstance(h, str):
        return h

    def work():
        user32.PostMessageW(h, win32con.WM_CLOSE, 0, 0)
        return f"close request sent to window {h}."

    return _acting("close", h, work)


READ_ONLY = [list_windows, tree, read, capture]
ACTING = [invoke, type_text, keys, click_xy, menu, move, launch, close]


def build():
    """MCPServer (mcp 2.x) or FastMCP (1.x). The read-only four carry
    readOnlyHint; the acting ones do not - the hint has to be honest."""
    try:
        from mcp.server.mcpserver import MCPServer as _Server  # mcp >= 2
    except ImportError:  # pragma: no cover
        from mcp.server.fastmcp import FastMCP as _Server

    try:
        from mcp.types import ToolAnnotations

        read_only = ToolAnnotations(readOnlyHint=True)
    except Exception:  # noqa: BLE001
        read_only = None
    server = _Server(name="hands-off")
    for fn in READ_ONLY:
        (server.tool(annotations=read_only) if read_only is not None else server.tool())(fn)
    from hands_off.recipes import run_recipe

    for fn in ACTING + [run_recipe]:
        server.tool()(fn)
    return server


def selftest() -> int:
    """The read-only half against whatever is open, no MCP client."""
    print(list_windows()[:1500])
    first = _top_windows()[0]["hwnd"]
    print(tree(str(first), depth=2, max_lines=15))
    out = capture(str(first))
    print(out[0] if isinstance(out, list) else out)
    return 0 if isinstance(out, list) else 1


def main() -> None:
    if "--selftest" in sys.argv or sys.argv[1:2] == ["run"]:
        # A console in cp1252 can't print every window title.
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if "--selftest" in sys.argv:
        raise SystemExit(selftest())
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        from hands_off.recipes import main_cli

        raise SystemExit(main_cli(sys.argv[2:]))
    build().run()


if __name__ == "__main__":
    main()
