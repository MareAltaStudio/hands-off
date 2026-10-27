"""A/B: does creating the process through WMI keep a new program from taking the focus?

Run it while a PERSON is using the PC (typing, browsing): Windows decides who may take the
foreground from where the last real input came, so a scripted user can't stand in (measured
27/10: with a script as the user, both ways lost the focus 6 of 6 times).

Each program is opened twice, alternating: once as a plain child process (what `launch` does
today) and once created by WMI (Win32_Process.Create, parent = WmiPrvSE). No focus guard in
either: this measures the raw steal. Windows go to monitor 2 and are closed after.

    python launch_wmi_ab.py            # ~2 min
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
from hands_off import server  # noqa: E402

user32 = ctypes.windll.user32
OUT = HERE / "out"
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"


def spawn_wmi(line: str, cwd: str | None) -> int | None:
    import pythoncom
    import win32com.client
    pythoncom.CoInitialize()
    wmi = win32com.client.GetObject(r"winmgmts:\\.\root\cimv2")
    startup = wmi.Get("Win32_ProcessStartup").SpawnInstance_()
    startup.ShowWindow = 4  # SW_SHOWNOACTIVATE
    # pywin32 late binding can't call Win32_Process.Create directly ("'int' is not callable",
    # which made the first WMI attempt fall back to a plain child in silence): use ExecMethod_
    proc = wmi.Get("Win32_Process")
    args = proc.Methods_("Create").InParameters.SpawnInstance_()
    args.CommandLine = line
    if cwd:
        args.CurrentDirectory = cwd
    args.ProcessStartupInformation = startup
    out = proc.ExecMethod_("Create", args)
    if out.ReturnValue != 0:
        raise RuntimeError(f"WMI Create returned {out.ReturnValue}")
    return int(out.ProcessId)


def spawn_child(line: str, cwd: str | None) -> int:
    si = subprocess.STARTUPINFO()
    si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    si.wShowWindow = 4
    return subprocess.Popen(line, startupinfo=si, cwd=cwd).pid


def fg() -> tuple[int, int, str]:
    h = user32.GetForegroundWindow()
    b = ctypes.create_unicode_buffer(200)
    user32.GetWindowTextW(h, b, 200)
    return h, server._pid_of(h), b.value[:50]


# the executables whose windows count as "the program we opened": anything else that appears during
# a trial belongs to someone else (27/10 a first version closed another session's Blender)
OWN = {"charmap.exe": {"charmap.exe"}, "notepad.exe": {"notepad.exe"}, "chrome.exe": {"chrome.exe"},
       "calc.exe": {"applicationframehost.exe", "calculatorapp.exe"}}


def trial(mode: str, line: str, cwd: str | None) -> dict:
    exe = Path(line.split('"')[1] if line.startswith('"') else line.split()[0]).name.lower()
    own = OWN[exe]
    before_windows = {w["hwnd"] for w in server._top_windows()}
    h0, _, t0 = fg()
    (spawn_wmi if mode == "wmi" else spawn_child)(line, cwd)
    new, stolen_by = set(), None
    end = time.time() + 8
    while time.time() < end:
        for w in server._top_windows():
            if w["hwnd"] not in before_windows and w["exe"].lower() in own:
                new.add(w["hwnd"])
        h, _, t = fg()
        if h != h0 and h in new:
            stolen_by = t
        time.sleep(0.05)
    for h in new:
        server.move(str(h), 2, "bottom-right")
    time.sleep(0.5)
    for h in new:
        server.close(str(h))
    time.sleep(1.5)
    return {"mode": mode, "program": line.split('"')[1] if line.startswith('"') else line.split()[0],
            "user_window": t0, "stolen": bool(stolen_by), "by": stolen_by, "windows": len(new)}


def main() -> int:
    OUT.mkdir(exist_ok=True)
    note = OUT / "ab_note.txt"
    note.write_text("hands-off A/B\n")
    programs = [("charmap.exe", None), (f'notepad.exe "{note}"', None), ("calc.exe", None),
                (f'"{CHROME}" --guest --no-first-run --no-default-browser-check --new-window about:blank', None)]
    rows = []
    for i, (line, cwd) in enumerate(programs * 3):
        for mode in (("wmi", "child") if i % 2 == 0 else ("child", "wmi")):
            r = trial(mode, line, cwd)
            rows.append(r)
            print(json.dumps(r, ensure_ascii=False), flush=True)
    (OUT / "launch_wmi_ab.json").write_text(json.dumps(rows, indent=1, ensure_ascii=False))
    for mode in ("wmi", "child"):
        rs = [r for r in rows if r["mode"] == mode]
        print(f"{mode}: focus taken {sum(r['stolen'] for r in rs)}/{len(rs)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
