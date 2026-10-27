---
name: hands-off
description: Drive Windows programs without touching the user's mouse, keyboard or focus, through the `hands-off` MCP server (UI Automation + window messages, never SendInput) - list windows, read the tree of buttons and fields, press a button by name, write into a field, pick a menu item, send a key, click a point without moving the cursor, photograph a covered window, start and move programs to another monitor without stealing focus. Use when a task needs to click, fill in, save, export, confirm a dialog or read something on screen in a desktop program (installer, Save/Open dialog, Windows tool, desktop app), when the user says "do it without my mouse", "while I keep working", "click it for me", "press the button", or before reaching for any synthetic-input automation (SendInput, pyautogui, AutoHotkey).
---

# hands-off

The user keeps working while you operate their programs. Their cursor, their keyboard and the window they are typing
in are not yours. The server's docstring (`hands_off/server.py`) explains why each decision was made.

The tools show up as `mcp__hands-off__*` once the server is registered (`claude mcp add -s user hands-off -- uvx hands-off-mcp`).
If they don't: `claude mcp get hands-off`.

## Order of choice (always)
1. **The program's own API**: bpy (Blender), UXP/ExtendScript (Photoshop), CDP (Chrome/Electron), COM (Office),
   a CLI, a scripting console. Touches nothing on screen.
2. **hands-off**: UI Automation and window messages. Works on a covered window, on another monitor, while the user
   uses the PC.
3. **Synthetic mouse/keyboard**: only after asking ("I need your mouse for 10 s, ok?"). Never silently.

## The flow
1. `list_windows(filter)` → the window's number. Every other tool takes the number, `exe:name.exe` or part of the
   title. If more than one matches, the answer lists the numbers; pass the number.
2. `tree(window, depth, filter)` → controls with `#path`, type, name, `id=` and what they accept
   (invoke, toggle, value, expand, select). Use `filter` ("Button", "Edit", part of a name) on big windows.
   If it says "almost nothing through UIA", the program draws its own interface: go to `capture` + `click_xy`,
   or back to layer 1.
3. Act:
   - `invoke(window, target, action)`: click (default), toggle, select, expand, collapse.
   - `type_text(window, target, text, enter)`: replaces the field's whole value.
   - `menu(window, "File > Save As")`: on a classic menu it sends WM_COMMAND and nothing opens on screen.
   - `keys(window, "f5")`, `click_xy(window, x, y)`.
   - `target` = `#2.0.5` (path from the tree), `Type:Name` (`Button:Save`, `Edit:Find what`), `Name` or
     `id=AutomationId`. Names match exactly first, then by substring; when there is more than one candidate, the
     answer says so.
4. **Always check**: `read(window, target)` for a value or state, `capture(window[, target])` for the picture. A
   window message has no confirmation; only the check proves it worked.
5. A program to test with: `launch(command, arguments, monitor=2)` starts it on monitor 2 without focus.
   `move(window, 2)` brings an existing one. When done: `close(window)`, the same as its X (if something is unsaved,
   the program asks; answer the dialog with `tree`/`invoke`).

## Scale: explore once, then write a recipe
Driving a program step by step costs one agent turn per click, and each turn is a fresh judgement. That is right the
first time, when nobody knows the path yet. It is waste the tenth time. So a task that will repeat goes through three
stages:

1. **Explore** with the tools above: find the windows, the targets, the order, the checks that prove it worked.
2. **Freeze** what worked into a recipe (`recipes/<task>.json`): the same steps as tool calls, plus `wait`, `check`,
   `sleep` and `python` steps. Write it right after a successful run, while the targets are known.
3. **Run** it in one call (`run_recipe(path, values)`) or with no agent at all (`hands-off-mcp run task.json a=1`),
   from a scheduler, a script or another tool. The agent comes back only when the report says it stopped.

A recipe is not just clicks. Mix the layers in it: a `python` step that calls a program's API or prepares a file,
then `invoke`/`type_text` for the dialog that has no API, then a `check`. The cheapest layer that does each step wins,
same as the order of choice.

Rules for a recipe that can run unattended:
- **Name windows by `exe:` or title, and keep numbers with `"as"`.** A window number changes on every run; a number
  written in the file breaks the second time. UWP apps live inside `ApplicationFrameHost.exe`, so keep the number
  `launch` returns.
- **Targets by `id=` first**, then `Type:Name`. `#paths` move when the program's layout changes; names change with
  the program's language.
- **`wait` before acting on anything that appears** (a window, a dialog, a button that loads late), never `sleep`
  and hope.
- **End with a `check`** on what the task was supposed to change. A recipe without a check is not finished. Prefer
  `matches` with anchors: `contains "2"` passes on "12".
- **`finally` closes what the recipe opened**, so a failed run leaves nothing behind.
- `${name}` fills from `vars`, the caller's values and every `as`: one recipe, many inputs.
- When a recipe stops, fix it from the report (which step, what it saw) and run it again; don't take over by hand
  and leave the file stale.

Example: [`recipes/calculator_add.json`](../../recipes/calculator_add.json).

## What works and what doesn't (measured)
| Program | Result |
|---|---|
| Win32/MFC (msinfo32) | full tree; menu by WM_COMMAND; field by UIA Value; button by BM_CLICK; clicks and arrows by message |
| WinUI (new Notepad) | write (Value), read the text, File > Save by Invoke |
| UWP (Calculator) | buttons by `id=num7Button`..., display read by `id=CalculatorResults` |
| Chrome/Edge/Electron (web page) | the tree only shows the browser chrome (page content needs a screen reader active). `click_xy` reaches the page as a **real** click (`isTrusted: true`) without moving the cursor. Find the point with JS (`getBoundingClientRect`) and **confirm it with `elementFromPoint` before clicking**: a wrong point clicks the wrong thing. Switching tabs: `invoke(..., "TabItem:<title>", "select")` |
| Godot, custom-drawn UIs | `capture` only; the tree comes back empty |
| Games, the Photoshop canvas, the Blender viewport | **no**: they read the real mouse. Use layer 1 |

## The traps (measured)
- **WinUI/UWP apps try to take the focus on every action.** While an action runs, the target's window carries
  `WS_EX_NOACTIVATE`, so it can't (Calculator: 0 of 146 samples off the user's window). On classic Win32 controls
  messages go first, because UIA `Value`/`Select`/`Toggle` focus the control. The guard still watches the foreground
  for 0.9 s as a backstop and only pulls focus back when the TARGET program took it. If an answer says
  `could NOT give it back`, tell the user (the message says who has the focus now).
- **A program that is starting can take the focus.** `launch` creates it through WMI, whose parent has no right to
  the foreground (with a person using the PC: 2 of 18 launches took the focus, against 12 of 20 as a plain child;
  both were Calculator, a UWP app the system activates itself). Documents open with their associated program, not
  through `cmd start`. A program started this way gets the user's default environment, not the server's: if it
  needs a variable the server has, pass it in `arguments`.
- **`id=` can repeat down a Win32 wrapper chain.** In the Open/Save dialog `id=1148` is the ComboBoxEx, its
  ComboBox and the Edit; hands-off picks the deepest that can act and says so. If text still lands in the wrong
  place, target the `#path` from `tree()`.
- **A test that closes windows closes only its own.** Other programs, and other agents, open windows while you
  work: match by the process you started (exe or pid), never by "any new window".
- The foreground passes through "no window" during the switch: checking on the very next line gives a false
  "failed". That is why the guard retries every 30 ms instead of checking once.
- **Capture**: PrintWindow **with** `PW_RENDERFULLCONTENT` takes covered windows, GPU-rendered ones included. The
  classic black picture comes from calling it without the flag. If the picture is still black, it falls back to
  Windows Graphics Capture on its own. A minimised window can't be captured: `move` it first.
- `capture` shrinks the image to `max_width`. `click_xy` coordinates are the whole window at scale 1:
  `x = crop + px / scale` (the answer of `capture` carries the formula).
- **Classic (MFC) menus**: a check mark only refreshes when the menu is shown on screen, so it can be stale. Don't
  trust the mark; check with `capture`.
- **ctrl/alt shortcuts through `keys` fail in many programs**, because they read the real keyboard state. Prefer
  `menu` or `invoke` on the button.
- `invoke` on a button that opens a modal dialog may never return. It runs on a thread with a 4 s limit and answers
  "pending": the dialog is open, look at `list_windows()` and treat the dialog as another window.
- All UIA work runs on a single thread (COM MTA). One hung call makes the next ones wait up to 30 s.
- Programs that restore their previous session (the new Notepad reopens its tabs) carry the user's work: write only
  in your own test file and don't close their tabs.
- Every acting call is logged to `%LOCALAPPDATA%\hands-off\actions.log` (or `HANDS_OFF_LOG`).
