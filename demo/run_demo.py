"""Record the demo video in one take: the "user" draws in Paint on monitor 1 while hands-off
drives Mouse Properties and Character Map on monitor 2.

Run it only when nobody is using the PC: fake_user.py moves the real cursor.

    python run_demo.py                 # full take (~35 s), then compose
    python run_demo.py --seconds 10    # rehearsal
    python run_demo.py --test-capture  # 3 s screen capture only, to check the geometry

Outputs in demo/out/: raw_m1.mkv, raw_m2.mkv (one per monitor), split.mp4 (side by side, 1920x540),
focus_log.jsonl, actions.log, data.json (what the overlay reads).
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
REPO = HERE.parent
PY = sys.executable
sys.path.insert(0, str(REPO / "src"))

import ctypes  # noqa: E402

user32 = ctypes.windll.user32
ctypes.windll.shcore.SetProcessDpiAwareness(2)


def ffmpeg_exe() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        out = subprocess.run(["uvx", "--from", "imageio-ffmpeg", "python", "-c",
                              "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"],
                             capture_output=True, text=True, check=True)
        return out.stdout.strip().splitlines()[-1]


def monitors():
    from ctypes import wintypes
    found = []
    proto = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                               ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)

    def cb(h, dc, r, lp):
        rc = r.contents
        found.append((rc.left, rc.top, rc.right, rc.bottom))
        return 1
    user32.EnumDisplayMonitors(0, 0, proto(cb), 0)
    primary = next(m for m in found if m[0] == 0 and m[1] == 0)
    other = next(m for m in found if m != primary)
    return primary, other


def start_captures(ff: str) -> list[subprocess.Popen]:
    """Two captures, both stamped with the wall clock so they can be lined up afterwards:
    monitor 1 through Desktop Duplication (ddagrab, GPU, full frame rate) and monitor 2,
    which sits on another adapter that ddagrab can't reach, through gdigrab (~27 fps at
    1920x1080; the whole 4480-wide desktop through gdigrab only made 10 fps)."""
    (pl, pt, pr, pb), (ol, ot, orr, ob) = monitors()
    # encoded on the GPU (NVENC): with x264 on the CPU and Blender running, monitor 1 fell to 18 fps
    common = ["-copyts", "-c:v", "h264_nvenc", "-preset", "p4", "-tune", "ll", "-rc", "vbr", "-cq", "19",
              "-f", "matroska"]
    m1 = [ff, "-y", "-hide_banner", "-loglevel", "error", "-use_wallclock_as_timestamps", "1",
          "-f", "lavfi", "-i", "ddagrab=output_idx=0:framerate=60:draw_mouse=1",  # frames stay on the GPU
          *common, str(OUT / "raw_m1.mkv")]
    m2 = [ff, "-y", "-hide_banner", "-loglevel", "error", "-use_wallclock_as_timestamps", "1",
          "-f", "gdigrab", "-framerate", "30", "-draw_mouse", "1", "-offset_x", str(ol), "-offset_y", str(ot),
          "-video_size", f"{orr - ol}x{ob - ot}", "-i", "desktop", *common, str(OUT / "raw_m2.mkv")]
    return [subprocess.Popen(c, stdin=subprocess.PIPE) for c in (m1, m2)]


def stop_captures(ps: list[subprocess.Popen]) -> None:
    for p in ps:
        try:
            p.stdin.write(b"q")
            p.stdin.flush()
        except OSError:
            pass
    for p in ps:
        p.wait(timeout=60)


def start_time(ff: str, path: Path) -> float:
    """Wall-clock time of the file's first frame (it was recorded with -copyts)."""
    import re
    info = subprocess.run([ff, "-hide_banner", "-i", str(path)], capture_output=True, text=True).stderr
    return float(re.search(r"start: ([0-9.]+)", info).group(1))


def compose(ff: str, t0: float, seconds: float, out: Path) -> None:
    """Left = monitor 1 (the user), right = monitor 2 (the agent), each 960x540, both cut
    from the same wall-clock instant t0."""
    (pl, pt, pr, pb), _ = monitors()
    # monitor 1: a 16:9 crop that leaves the taskbar out (the bottom 5%); monitor 2 loses its
    # bottom 60 px: its auto-hidden taskbar pops up when a program flashes
    h1 = int((pb - pt) * 0.95) // 2 * 2
    w1 = (h1 * 16 // 9) // 2 * 2
    x1 = ((pr - pl) - w1) // 2
    # ffmpeg rebases each input to its first frame, so cut each one at t0 minus its own start
    c1, c2 = (f"trim=start={t0 - start_time(ff, OUT / n):.3f}:duration={seconds:.3f},setpts=PTS-STARTPTS"
              for n in ("raw_m1.mkv", "raw_m2.mkv"))
    flt = (f"[0:v]{c1},crop={w1}:{h1}:{x1}:0,scale=960:540,fps=60[a];"
           f"[1:v]{c2},crop=1812:1020:54:0,scale=960:540,fps=60[b];[a][b]hstack=inputs=2[v]")
    subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(OUT / "raw_m1.mkv"),
                    "-i", str(OUT / "raw_m2.mkv"), "-filter_complex", flt, "-map", "[v]",
                    "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p", str(out)], check=True)


def find_window(part: str, timeout: float = 15.0) -> int:
    from hands_off import server
    end = time.time() + timeout
    while time.time() < end:
        for w in server._top_windows():
            if part.lower() in (w["title"] + " " + w["exe"]).lower():
                return w["hwnd"]
        time.sleep(0.3)
    raise RuntimeError(f"no window matching {part!r}")


CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
BLENDER_DOCS = "https://docs.blender.org/manual/en/latest/modeling/modifiers/generate/subdivision_surface.html"

# The programs hands-off drives on monitor 2: name -> (command, arguments, corner, maximise)
APPS = {
    "mouse": ("rundll32.exe", "shell32.dll,Control_RunDLL main.cpl", "top-right", False),
    "charmap": ("charmap.exe", "", "bottom-left", False),
    "calc": ("calc.exe", "", "bottom-right", False),
    # a guest window: no profile, no sign-in prompts, nothing personal
    "chrome": (CHROME, "--guest --no-first-run --no-default-browser-check --disable-renderer-backgrounding "
               "--disable-background-timer-throttling --disable-backgrounding-occluded-windows "
               f"--new-window {BLENDER_DOCS}", "top-left", True),
}
# what each program shows once it is ready: the take waits for it (a page still loading ate the clicks)
READY = {
    "chrome": "Subdivision Surface Modifier",
}


BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.0\blender.exe"


def wait_ready(h: int, title: str, timeout: float = 60.0) -> None:
    """Wait until the window's title says the content arrived AND its picture isn't blank."""
    import win32gui
    from hands_off import server
    end = time.time() + timeout
    while time.time() < end:
        if title in win32gui.GetWindowText(h):
            img, _ = server._grab(h)
            lo, hi = img.convert("L").getextrema()
            if hi - lo > 100:  # text and images, not a flat loading page
                time.sleep(1.5)
                return
        time.sleep(0.5)
    raise RuntimeError(f"window {h} never showed {title!r}")


def setup(primary, apps: list[str], user_app: str = "paint") -> dict:
    """Runs while the PC is free, so taking the focus here is fine."""
    from hands_off import server
    win = {}
    win["backdrop"] = subprocess.Popen([PY, str(HERE / "backdrop.py")])
    time.sleep(1.5)
    for name in apps:
        cmd, args, corner, maximise = APPS[name]
        r = server.launch(cmd, args, monitor=2, corner=corner, wait_s=30)
        win[name] = int(r.split()[1])
        if maximise:
            user32.ShowWindow(win[name], 3)  # SW_MAXIMIZE, on the monitor it was moved to
        if name in READY:
            wait_ready(win[name], READY[name])
        time.sleep(2.0)
    if user_app == "blender":
        # factory settings: no add-ons, recent files or preferences of the user on screen
        scene = OUT / "scene.blend"
        if not scene.exists():
            subprocess.run([BLENDER, "--background", "--factory-startup", "--python", str(HERE / "make_scene.py"),
                            "--", str(scene)], capture_output=True, check=True)
        r = server.launch(BLENDER, f'--factory-startup "{scene}"', wait_s=60)
        time.sleep(4.0)
    else:
        r = server.launch("mspaint.exe", wait_s=20)
    # the NEW window, not one of the user's own Blender or Paint windows
    paint = int(r.split()[1])
    for name in apps:  # in front of the backdrop, whatever order the windows appeared in
        user32.SetWindowPos(win[name], 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)  # HWND_TOP, no move/size/activate
    l, t, rr, b = primary
    user32.ShowWindow(paint, 9)  # SW_RESTORE
    user32.SetWindowPos(paint, 0, l + 50, t + 50, 1200, 800, 0x0004)
    user32.ShowWindow(paint, 3)  # SW_MAXIMIZE
    win["paint"] = paint
    time.sleep(1.0)
    return win


def teardown(win: dict) -> None:
    from hands_off import server
    for k in APPS:
        if k in win:
            server.close(str(win[k]))
    if "paint" in win:
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(win["paint"], ctypes.byref(pid))
        subprocess.run(["taskkill", "/PID", str(pid.value), "/F"], capture_output=True)
    if "backdrop" in win:
        win["backdrop"].terminate()


def tail_actions(log: Path, t0: float, sink: list, stop: threading.Event) -> None:
    """Stamp each hands-off action with our own clock (the log has 1-s resolution)."""
    pos = 0
    while not stop.is_set():
        if log.exists():
            with open(log, encoding="utf-8") as f:
                f.seek(pos)
                for line in f:
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) >= 4:
                        sink.append({"t": round(time.time() - t0, 2), "tool": parts[1], "text": parts[3]})
                pos = f.tell()
        time.sleep(0.05)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=32)
    ap.add_argument("--lead", type=float, default=3.0, help="seconds of drawing before the agent starts")
    ap.add_argument("--test-capture", action="store_true")
    ap.add_argument("--recipe", default=str(HERE / "demo_actions.json"))
    ap.add_argument("--user-app", choices=("paint", "blender"), default="paint")
    ap.add_argument("--apps", default="mouse,charmap", help=f"programs for the agent, from {', '.join(APPS)}")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    ff = ffmpeg_exe()

    if a.test_capture:
        caps = start_captures(ff)
        time.sleep(1.5)
        t0 = time.time()
        time.sleep(3)
        stop_captures(caps)
        compose(ff, t0, 3, OUT / "test_split.mp4")
        print("ok:", OUT / "test_split.mp4")
        return 0

    primary, _ = monitors()
    actions_log = OUT / "actions.log"
    actions_log.unlink(missing_ok=True)
    print("Setting up. From now on, don't touch the mouse. Esc stops the user script.")
    win = setup(primary, a.apps.split(","), a.user_app)
    try:
        for i in (3, 2, 1):
            print(f"recording in {i}...")
            time.sleep(1)
        caps = start_captures(ff)
        time.sleep(1.5)  # ffmpeg warm-up
        t0 = time.time()
        (OUT / "t0.txt").write_text(repr(t0))
        user = subprocess.Popen([PY, str(HERE / "fake_user.py"), "--seconds", str(a.seconds),
                                 "--log", str(OUT / "focus_log.jsonl"), "--t0-file", str(OUT / "t0.txt"),
                                 "--app", a.user_app])
        time.sleep(a.lead)
        acts: list = []
        stop = threading.Event()
        th = threading.Thread(target=tail_actions, args=(actions_log, t0, acts, stop), daemon=True)
        th.start()
        env = dict(os.environ, HANDS_OFF_LOG=str(actions_log))
        rec = subprocess.run([PY, "-m", "hands_off", "run", a.recipe,
                              *(f"{k}={win[k]}" for k in APPS if k in win)],
                             env=env, capture_output=True, text=True, cwd=str(REPO / "src"))
        print(rec.stdout)
        user_rc = user.wait()
        time.sleep(1.0)
        stop.set()
        th.join()
        stop_captures(caps)
        length = time.time() - t0
    finally:
        teardown(win)

    focus = [json.loads(x) for x in (OUT / "focus_log.jsonl").read_text(encoding="utf-8").splitlines() if x]
    lost = [f for f in focus if not f["fg_is_paint"]]
    (OUT / "data.json").write_text(json.dumps({"focus": focus, "ticker": acts}, indent=1), encoding="utf-8")
    compose(ff, t0, length, OUT / "split.mp4")
    print(f"recipe: {'ok' if rec.returncode == 0 else 'FAILED'}; user script exit {user_rc}; "
          f"{len(acts)} actions; focus samples {len(focus)}, not on Paint: {len(lost)}")
    for f in lost[:10]:
        print("  focus lost:", f)
    return 0 if rec.returncode == 0 and user_rc == 0 and not lost else 1


if __name__ == "__main__":
    raise SystemExit(main())
