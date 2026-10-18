# How it works

hands-off has one rule: **never touch the user's input**. No `SendInput`, no `SetCursorPos`, no focusing a window on
purpose. Everything below follows from that rule.

## The layers

Every acting tool tries the layers in order and its answer names the one that did the work.

| Layer | Mechanism | Needs the window in front? | Moves the cursor? |
|---|---|---|---|
| 1. UI Automation | `Invoke`, `Toggle`, `Value`, `ExpandCollapse`, `SelectionItem`, `LegacyIAccessible` patterns | no | no |
| 2. Window messages | `BM_CLICK`, `WM_SETTEXT`, `WM_COMMAND`, `WM_LBUTTONDOWN/UP`, `WM_KEYDOWN/UP`, `WM_CHAR` posted to the window | no | no |
| 3. — | nothing; the answer says the program needs its own API | — | — |

There is deliberately no third layer that falls back to synthetic input. A tool that "sometimes" grabs your mouse is
a tool you can't leave running while you work.

### Why UI Automation first

UIA finds controls by **name, type and AutomationId**, so a target like `Button:Save` or `id=num7Button` survives a
window being resized, moved to another monitor or covered by other windows. Its patterns are the program's own
accessibility contract, the same one a screen reader uses, so the program handles the action exactly as if a user
had done it.

### When messages take over

Some controls expose no usable pattern. For those, hands-off posts the message the control would have received from a
real click or key press, addressed to the control's own window handle. Classic menus are the best case: `WM_COMMAND`
with the item's id runs the command without the menu ever opening on screen.

Messages carry no confirmation, which is why every tool tells the agent to check the result with `read` or `capture`.

### Chromium and Electron

Chrome, Edge and Electron draw the page into a child window named `Intermediate D3D Window`, which only shows pixels;
input posted there is dropped. hands-off skips it and posts to the render widget above it, where the click arrives as
a trusted event (`isTrusted: true`).

## The focus guard

WinUI and UWP apps take the foreground whenever one of their buttons is pressed, even through UIA. Without a guard,
the user's next keystroke would land in the wrong program.

After every acting tool hands-off:

1. watches the foreground window for 0.9 s (1.5 s after `launch`);
2. if the **target program** took it, hands it back to the window the user was in, retrying every 30 ms, because the
   foreground passes through "no window" during a switch and a single check gives false failures;
3. falls back to `SwitchToThisWindow` when the foreground lock refuses `SetForegroundWindow`, which happens about
   once in seven launches of an app that is still activating;
4. judges by where the focus **ended**, and says so in the answer.

It only undoes a steal by the target program. If the user switches windows themselves during that time, their choice
stands.

Measured: 11–79 ms per button press in Calculator; about 0.6 s on Notepad's *File > Save*.

## Capture

`capture` uses `PrintWindow` with `PW_RENDERFULLCONTENT`. That flag is what makes covered and GPU-rendered windows
come out right; calling `PrintWindow` without it gives the familiar black image. If the picture still comes back
black, it falls back to Windows Graphics Capture.

The process is DPI-aware (per-monitor v2), so UIA rectangles, window rectangles and captured pixels are in the same
physical-pixel space, and a point measured on a capture lands where it should.

## Threading

All UIA calls run on **one** worker thread with COM initialised as multithreaded. UIA calls coming from random pool
threads are a common way to leave a COM server wedged.

`Invoke` runs on a throwaway thread with a 4-second limit, because a Win32 button that opens a modal dialog doesn't
return from `Invoke` until the dialog closes. After 4 s the answer is "pending": the dialog is open and can be handled
as another window.

One hung call makes the next ones wait (up to 30 s); the answer says so.

## The action log

Every acting call is one line in `%LOCALAPPDATA%\hands-off\actions.log` (override with `HANDS_OFF_LOG`): time, tool,
window, first line of the answer. Writing the log never costs the action.
