# hands-off

**Your AI agent uses your Windows programs while you keep using your PC.**

An MCP server that lets Claude (or any MCP client) click buttons, fill in fields, pick menu items and read what's on
screen in desktop programs **without moving your mouse, typing on your keyboard or stealing the window you're in**.

## Why

Most desktop automation for agents works through synthetic input: SendInput, pyautogui, AutoHotkey. Windows has one
cursor and one foreground window per session, so while the agent works, you can't. Every "save this", "confirm that
dialog", "export the file" means taking your hands off the mouse and waiting.

hands-off never calls SendInput and never moves the cursor. It works in layers, and every answer says which one did
the job:

1. **UI Automation patterns** (Invoke, Toggle, Value, ExpandCollapse, SelectionItem, LegacyIAccessible): controls
   found by name, on a window that can be covered or on another monitor.
2. **Window messages** (BM_CLICK, WM_SETTEXT, WM_COMMAND, mouse and key messages posted to the window): no cursor
   involved.
3. **Nothing else.** If a program only reads the real mouse, the tool says so instead of quietly grabbing your
   cursor.

On top of that:

- **Focus guard.** Modern apps (WinUI/UWP) grab the foreground when you press their buttons. After every action
  hands-off watches the foreground and hands it back to where you were, in 11-79 ms in our measurements. It only
  undoes a steal by the *target* program, so it never fights you switching windows.
- **Capture of covered windows.** PrintWindow with `PW_RENDERFULLCONTENT`, which also works for GPU-rendered windows,
  with Windows Graphics Capture as the fallback.
- **An action log** of every acting call, at `%LOCALAPPDATA%\hands-off\actions.log`.

## Tools

| Tool | What it does |
|---|---|
| `list_windows` | open windows: number, program, monitor, title |
| `tree` | the window's controls with paths, names, ids and what they accept |
| `read` | a control's value, text, checked/expanded state, rectangle |
| `capture` | a picture of the window (or one control), even when it's covered |
| `invoke` | click, toggle, select, expand or collapse a control by name |
| `type_text` | replace a field's value |
| `menu` | pick `File > Save As` (classic menus without opening anything on screen) |
| `keys` | send keys by message (`enter`, `esc`, `f5`, `down`...) |
| `click_xy` | click a point of the window without moving the cursor |
| `move` | move a window to another monitor without focusing it |
| `launch` | start a program without stealing focus, optionally on another monitor |
| `close` | ask a window to close, like its X button |

| `run_recipe` | run a recipe: a whole task in one call (see below) |

The first four are marked read-only (`readOnlyHint`), so a client can allow them without asking.

## Recipes: explore once, then stop paying for it

Driving a program click by click costs one agent turn per click. That's fine the first time, when the path is
unknown, and wasteful every time after. So once the agent has figured out a task, it writes the path down as a
**recipe**: the same tool calls as JSON, plus `wait`, `check`, `sleep` and `python` steps.

```json
{
  "name": "add two digits in Calculator",
  "vars": {"a": "7", "b": "5", "sum": "12"},
  "steps": [
    {"do": "launch", "command": "calc.exe", "monitor": 2, "corner": "bottom-right", "as": "calc"},
    {"do": "wait", "window": "${calc}", "target": "id=num7Button"},
    {"do": "invoke", "window": "${calc}", "target": "id=num${a}Button"},
    {"do": "invoke", "window": "${calc}", "target": "id=plusButton"},
    {"do": "invoke", "window": "${calc}", "target": "id=num${b}Button"},
    {"do": "invoke", "window": "${calc}", "target": "id=equalButton"},
    {"do": "check", "window": "${calc}", "target": "id=CalculatorResults", "matches": " ${sum}'$"}
  ],
  "finally": [{"do": "close", "window": "${calc}"}]
}
```

Run it in one MCP call (`run_recipe`) or with no agent at all:

```powershell
hands-off-mcp run recipes/calculator_add.json a=9 b=4 sum=13
```

It stops at the first error or failed `check` and reports which step and what it saw; `finally` cleans up either
way. A `python` step can call a program's own API in the middle of the recipe, so the cheapest layer does each step.
The agent only comes back when a recipe breaks.

## What works

| Program | Result |
|---|---|
| Win32 / MFC | full tree, menus, fields, buttons |
| WinUI (new Notepad), UWP (Calculator) | fields, buttons, menus; the focus guard handles their focus grabs |
| Chrome / Edge / Electron | browser UI through the tree; the page through `click_xy`, which arrives as a trusted click |
| Custom-drawn UIs (Godot, PureRef) | `capture` only |
| Games, the Photoshop canvas, the Blender viewport | **no**: they read the real mouse. Use the program's own API |

## Install

Requires Windows 10/11 and Python 3.10+.

```powershell
claude mcp add -s user hands-off -- uvx --from git+https://github.com/MareAltaStudio/hands-off hands-off-mcp
```

Or from a clone:

```powershell
git clone https://github.com/MareAltaStudio/hands-off
cd hands-off
uv venv; uv pip install -e .
claude mcp add -s user hands-off -- "$PWD\.venv\Scripts\hands-off-mcp.exe"
```

Any other MCP client: run `hands-off-mcp` (stdio).

Check it without a client: `hands-off-mcp --selftest` lists your windows, walks one tree and takes one capture.

## The skill

The server gives the agent hands; [`skills/hands-off/SKILL.md`](skills/hands-off/SKILL.md) tells it how to use them:
the order of choice (the program's API first, hands-off second, the real mouse only after asking), the
list → tree → act → check loop, and the traps we measured. For Claude Code, copy the folder into
`~/.claude/skills/`.

In our own use the server and the skill only work well together. The server alone lets the agent act; the skill
keeps it from guessing.

## Safety

hands-off acts on your real programs with your user's rights. It can press "Delete", close a window or confirm a
dialog. Leave the acting tools behind your client's permission prompt until you trust the flow, and read the action
log when something surprises you.

## License

MIT
