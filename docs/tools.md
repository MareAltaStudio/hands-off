# Tool reference

Every tool answers in text. Failures start with `[error]` and are never raised as exceptions, so the agent can read
them and adjust.

## Addressing a window

Every tool that takes `window` accepts:

| Form | Example | Notes |
|---|---|---|
| number | `"393772"` | from `list_windows`; changes every time the program starts |
| `exe:` | `"exe:notepad.exe"` | the program's executable; UWP apps live in `ApplicationFrameHost.exe` |
| title | `"Untitled - Notepad"` | exact match first, then substring |

If more than one window matches, the answer lists them and asks for the number.

## Addressing a control

Tools that take `target` accept:

| Form | Example | Notes |
|---|---|---|
| `#path` | `"#2.0.5"` | child indices from `tree`; shifts when the layout changes |
| `Type:Name` | `"Button:Save"` | type as shown by `tree` |
| `Name` | `"Save"` | exact first, then substring; enabled and on-screen controls win |
| `id=` | `"id=num7Button"` | AutomationId; the most stable, use it when there is one |

When several controls match, the first usable one is taken and the answer says how many there were.

## Read-only tools

These carry `readOnlyHint`, so a client can allow them without asking.

### `list_windows(filter="")`
Open, visible, non-cloaked windows: number, executable, monitor (`m1`, `m2`...), `[min]` if minimised, title.
`filter` matches part of the title or the executable.

### `tree(window, depth=6, filter="", max_lines=250)`
The UIA tree as indented lines: `#path Type 'Name' id=... (patterns) [disabled] [offscreen]`. Patterns tell what
the control accepts: `invoke`, `toggle`, `value`, `expand`, `select`, `text`, `range`, `scroll`. `filter` keeps only
matching lines but still walks everything. Walks stop at 4,000 nodes.

An answer that says "almost nothing through UIA" means the program draws its own interface: use `capture` +
`click_xy`, or the program's API.

### `read(window, target)`
One control: description, `value`, `checked`, `expanded`, `selected`, `text` (up to 4,000 characters), `rect`,
`enabled`.

### `capture(window, target="", max_width=1600)`
A PNG of the window, or of one control when `target` is given, plus its scale and crop offset. Works on covered
windows; not on minimised ones (`move` restores them).

To click a point seen on the image: `x = crop_x + px / scale`, `y = crop_y + py / scale` (the answer carries the
numbers).

## Acting tools

Each one runs through the [focus guard](how-it-works.md#the-focus-guard) and is written to the action log.

### `invoke(window, target, action="click")`
`action`: `click`, `toggle`, `select`, `expand`, `collapse`. For `click` the order is: `BM_CLICK` on classic buttons,
UIA Invoke, Toggle, SelectionItem, ExpandCollapse, MSAA default action, and finally a click message at the control's
centre. An Invoke that doesn't return within 4 s answers "pending" (a modal dialog opened).

### `type_text(window, target, text, enter=False)`
Replaces the field's whole value: UIA Value, else `WM_SETTEXT` on classic edit controls, else characters posted one by
one. Empty `target` = the control that has keyboard focus inside the window.

### `keys(window, combo, target="")`
Posts key messages: `enter`, `esc`, `tab`, `space`, `backspace`, `delete`, arrows (`up`/`down`/`left`/`right`),
`home`, `end`, `pgup`, `pgdn`, `f1`–`f12`, single characters, joined with `+` (`ctrl+s`). Many programs read the
real keyboard state for ctrl/alt shortcuts and ignore these; prefer `menu` or `invoke`.

### `click_xy(window, x, y, button="left", double=False)`
A mouse message to the deepest child window under the point. `x`, `y` in pixels of the whole window. `button`:
`left`, `right`, `middle`.

### `menu(window, path)`
`"File > Save As"` (also `->` or `/`). Classic menus get `WM_COMMAND` directly; modern ones are expanded and invoked
through UIA, including popups that live in their own top-level windows. Labels are matched as the program shows them,
in its own language.

### `move(window, monitor=2, corner="top-left")`
Moves the window to a monitor (1 = primary, then the others) without focusing it, restoring it if minimised.
`corner`: `top-left`, `top-right`, `bottom-left`, `bottom-right`.

### `launch(command, arguments="", monitor=0, corner="top-left", wait_s=15)`
Starts a program without activating it and returns the new window's number. A document path opens in its associated
program. `monitor` > 0 moves the new window there.

### `close(window)`
Posts `WM_CLOSE`, the same as the window's X button. Unsaved work makes the program ask; answer the dialog with
`tree` / `invoke`.

### `run_recipe(recipe, values=None)`
Runs a [recipe](recipes.md): a path to a `.json` file or the JSON itself. `values` fills its `${variables}`.
