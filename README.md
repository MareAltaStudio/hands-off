<div align="center">

# hands-off

**Your AI agent uses your Windows programs while you keep using your PC.**

An MCP server that clicks buttons, fills in fields, picks menu items and reads the screen in desktop programs<br>
**without moving your mouse, typing on your keyboard or stealing the window you're in.**

[![CI](https://github.com/MareAltaStudio/hands-off/actions/workflows/ci.yml/badge.svg)](https://github.com/MareAltaStudio/hands-off/actions/workflows/ci.yml)
![Windows 10 | 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4)
![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)
![MCP](https://img.shields.io/badge/MCP-server-6E56CF)
[![License: MIT](https://img.shields.io/badge/License-MIT-green)](LICENSE)

[Quick start](#quick-start) · [How it works](docs/how-it-works.md) · [Tools](docs/tools.md) · [Recipes](docs/recipes.md) · [Compatibility](docs/compatibility.md)

</div>

<p align="center">
  <img src="docs/media/demo.gif" alt="Left: a script orbits a Blender scene with the real cursor. Right: Claude, through hands-off, clicks through the Blender manual in a browser on the other monitor. The focus stays on Blender the whole time." width="960">
</p>

<p align="center"><sub>One take, no cuts. The left side is a script moving the real cursor. Full video with narration in the <a href="https://github.com/MareAltaStudio/hands-off/releases/tag/v0.1.0">v0.1.0 release</a>; how it was made: <a href="demo/README.md">demo/</a>.</sub></p>

---

## The problem

Desktop automation for agents usually works through synthetic input: `SendInput`, pyautogui, AutoHotkey. Windows has
**one cursor and one foreground window** per session, so while the agent works, you don't. Every "save this",
"confirm that dialog", "export the file" means taking your hands off the mouse and waiting.

## What hands-off does instead

|  | Synthetic input | hands-off |
|---|---|---|
| Moves your cursor | yes | **never** |
| Types into whatever window has focus | yes | **never** — messages go to the target window |
| Needs the window in front | yes | **no** — covered, on another monitor, all fine |
| Finds controls by | pixel coordinates | **name, type, AutomationId** |
| Knows if it worked | no | **says which layer acted; `read`/`capture` to check** |
| Steals focus | yes | **no**: the target can't activate while it acts (0 samples off the user's window, measured); `launch` is best effort, see [compatibility](docs/compatibility.md#focus-on-launch) |

It works in layers, and every answer names the one that did the job:

1. **UI Automation patterns:** Invoke, Toggle, Value, ExpandCollapse, SelectionItem, LegacyIAccessible.
2. **Window messages:** `BM_CLICK`, `WM_SETTEXT`, `WM_COMMAND`, mouse and key messages posted to the window.
3. **Nothing else.** A program that only reads the physical mouse gets an honest "use its API", never a quiet
   cursor grab.

More in [How it works](docs/how-it-works.md).

## Quick start

Requires Windows 10/11 and [uv](https://docs.astral.sh/uv/) (or Python 3.10+ with pip).

**Claude Code**

```powershell
claude mcp add -s user hands-off -- uvx --from git+https://github.com/MareAltaStudio/hands-off hands-off-mcp
```

**Claude Desktop, Cursor and other MCP clients**

```json
{
  "mcpServers": {
    "hands-off": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/MareAltaStudio/hands-off", "hands-off-mcp"]
    }
  }
}
```

**Check it without a client**

```powershell
uvx --from git+https://github.com/MareAltaStudio/hands-off hands-off-mcp --selftest
```

Then ask your agent something like *"open Calculator on my second monitor and add 7 and 5 — don't touch my mouse."*

## Tools

| Read-only | |
|---|---|
| `list_windows` | open windows: number, program, monitor, title |
| `tree` | a window's controls with paths, names, ids and what each accepts |
| `read` | a control's value, text, state and rectangle |
| `capture` | a picture of the window or one control, even when it's covered |

| Acting | |
|---|---|
| `invoke` | click, toggle, select, expand or collapse a control by name |
| `type_text` | replace a field's value |
| `menu` | `File > Save As` (classic menus without opening anything on screen) |
| `keys` | send keys by message (`enter`, `esc`, `f5`, `down`...) |
| `click_xy` | click a point without moving the cursor |
| `move` | move a window to another monitor or corner, without focusing it |
| `launch` | start a program without stealing focus |
| `close` | close a window, like its X button |
| `run_recipe` | run a whole recorded task in one call |

Read-only tools carry `readOnlyHint`, so your client can allow them without asking. Full reference in
[docs/tools.md](docs/tools.md).

## Recipes: explore once, then stop paying for it

Driving a program click by click costs one agent turn per click. Fine the first time, wasteful every time after. Once
the agent has figured out a task, it freezes the path into a **recipe**: the same tool calls as JSON, plus `wait`,
`check`, `sleep` and `python` steps.

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

```powershell
hands-off-mcp run recipes/calculator_add.json a=9 b=4 sum=13
```

One MCP call (`run_recipe`), or no agent at all: a scheduler, a script, a build step. It stops at the first failed
step or `check` and reports what it saw; `finally` cleans up either way. A `python` step can call a program's own
API mid-recipe, so the cheapest layer does each step. The agent only comes back when a recipe breaks.

More in [docs/recipes.md](docs/recipes.md).

## The skill

The server gives the agent hands; [`skills/hands-off/SKILL.md`](skills/hands-off/SKILL.md) teaches it how to use them:
the order of choice (the program's API first, hands-off second, the real mouse only after asking), the
list → tree → act → check loop, when to turn a task into a recipe, and the traps we measured.

For Claude Code, copy the folder into `~/.claude/skills/`. In our use the two only shine together: the server lets
the agent act, the skill keeps it from guessing.

## What works

| | |
|---|---|
| ✅ Win32 / MFC | full tree, menus, fields, buttons |
| ✅ WinUI, UWP | fields, buttons, menus; `WS_EX_NOACTIVATE` keeps them from taking the focus |
| ✅ Chrome, Edge, Electron | browser UI through the tree; page content through `click_xy` (arrives as a trusted click) |
| 🟡 Custom-drawn UIs (Godot, PureRef) | `capture` only |
| ❌ Games, the Photoshop canvas, the Blender viewport | they read the physical mouse — use the program's API |

Details and caveats in [docs/compatibility.md](docs/compatibility.md).

## Safety

hands-off acts on your real programs with your rights. It can press "Delete", confirm a dialog or close unsaved work.
Keep the acting tools behind your client's permission prompt until you trust the flow, run only recipes you've read,
and check `%LOCALAPPDATA%\hands-off\actions.log` when something surprises you. See [SECURITY.md](SECURITY.md).

## Contributing

Compatibility reports, traps and example recipes are the most useful contributions. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Mare Alta
