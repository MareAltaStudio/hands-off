# Compatibility

Measured on Windows 11 25H2 (build 26200). Every row was driven with the user's mouse and keyboard untouched.

| Program | Kind | Tree | Act | Notes |
|---|---|---|---|---|
| System Information (msinfo32) | Win32 / MFC | full | menus by `WM_COMMAND`, fields by UIA Value, buttons by `BM_CLICK`, clicks and arrows by message | check marks on MFC menus refresh only when the menu is shown; confirm with `capture` |
| Notepad (Windows 11) | WinUI | full | write (Value), read the text, *File > Save* by Invoke | takes the focus on every action; the guard gives it back in ~0.6 s. It restores the previous session's tabs: write only in your own test file |
| Calculator | UWP | full | buttons by `id=num7Button`..., display read by `id=CalculatorResults` | the window belongs to `ApplicationFrameHost.exe`; keep the number `launch` returns |
| Chrome / Edge / Electron | Chromium | browser UI only | the page through `click_xy` (trusted click); tabs by `invoke(..., "TabItem:<title>", "select")` | page content isn't in the tree unless a screen reader is active. Find points with `getBoundingClientRect` and confirm with `elementFromPoint` before clicking. Typing into a page: `click_xy` the field, `type_text` with `enter=True`, and wait a second or two before judging with `capture`, which can still show the old frame |
| Godot, PureRef | custom-drawn | empty | `capture` only | |
| Games, Photoshop canvas, Blender viewport | raw input | — | **no** | they read the physical mouse; use the program's API (UXP, `bpy`...) |

## Focus on launch

During actions the guard has a clean record: 159 clicks, keys, typing and menu calls over 13 days of daily
use, none left the focus with the target. Programs that are *starting* are harder, because Windows lets a new process take the foreground
and refuses to hand it back to a background one. Measured over the same 13 days:

| Program | Launches | Focus kept by the new program |
|---|---|---|
| PureRef (Qt) | 104 | 80 |
| Blender | 71 | 38 |
| Chromium-based browser | 14 | 8 |
| Photoshop | 7 | 5 |

`launch` reports it every time (`could NOT give it back`), so the agent can warn you. Launching programs ahead of
time, before you start working, avoids it.

## Requirements

- Windows 10 1903+ or Windows 11 (Windows Graphics Capture needs 1903+).
- Python 3.10+.
- The server runs as your user: it can operate programs running at the same or lower integrity level. A program
  running as administrator can't be driven from a non-elevated server (Windows UIPI).

## Not supported

- Other operating systems.
- Programs on another desktop session (locked screen, RDP session of another user).
- Secure desktop prompts (UAC), by design of Windows.

Tested something not on the list? Open an issue with the program, its version and what worked.
