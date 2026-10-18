# Recipes

A recipe is a task the agent has already figured out, written down so it can run again **without the agent deciding
each step**.

## Why

Driving a program click by click costs one agent turn per action: read the tree, choose a target, act, check. The
first time, that judgement is the point, because nobody knows the path yet. The tenth time, it's latency and tokens
spent rediscovering the same path, with a fresh chance of a wrong guess at every step.

So a task that repeats goes through three stages:

```
explore  ──►  freeze  ──►  run
(tools,       (recipe       (one call, or no
 one turn      JSON)         agent at all)
 per step)
```

1. **Explore** with the tools: find the windows, the targets, the order, and a check that proves it worked.
2. **Freeze** what worked into `recipes/<task>.json`, right after a successful run, while the targets are known.
3. **Run** it with `run_recipe` (one MCP call) or `hands-off-mcp run <task>.json name=value` (no agent: a scheduler,
   a script, another tool). The agent comes back only when a recipe reports that it stopped.

## Format

```json
{
  "name": "what it does",
  "vars": {"name": "default value"},
  "steps": [
    {"do": "<tool or step>", "...": "its arguments", "as": "keep_window_number", "note": "shown in the report"}
  ],
  "finally": [
    {"do": "close", "window": "${keep_window_number}"}
  ]
}
```

### Steps

| `do` | Arguments | What it does |
|---|---|---|
| any tool | the tool's arguments | `invoke`, `type_text`, `menu`, `launch`... exactly as in the [tool reference](tools.md) |
| `wait` | `window`, optional `target`, `timeout` (s, default 15) | waits until the window (and the control inside it) exists |
| `check` | `window`, `target`, one of `contains` / `equals` / `matches` | reads the control and requires the text; fails the recipe otherwise |
| `sleep` | `s` | pauses; prefer `wait` |
| `python` | `script` (relative to the recipe file), `args`, `timeout` | runs a script with the server's Python; a non-zero exit stops the recipe |

### Variables

`${name}` is replaced in every string, from three sources (later wins): the recipe's `vars`, the caller's values,
and every `as` captured so far. An undefined variable stops the recipe with an error.

`as` on `launch` keeps the number of the window it opened; on `wait`, the number of the window it found.

### Checks

`check` looks only at what the control **says**: its name, value, text and state. Its rectangle is ignored, so a
number in the coordinates can't make a check pass by accident.

- `contains`: substring. Careful: `contains "2"` passes on `12`.
- `equals`: the whole value, name or text.
- `matches`: a regular expression. Anchor it: `" ${sum}'$"` matches `Display is 12'` and not `Display is 112'`.

### Stopping and cleaning up

The recipe stops at the first step whose answer starts with `[error]`, at a failed `check`, or when the focus guard
couldn't give the focus back. The report lists every step that ran and what it saw.

`finally` runs afterwards **either way**, with the variables captured so far, and doesn't stop on errors. Use it to
close what the recipe opened.

## Running

```powershell
hands-off-mcp run recipes/calculator_add.json a=9 b=4 sum=13
```

Exit code 0 when every step passed, 1 when the recipe stopped, 2 on usage errors.

From an agent: `run_recipe("C:\\path\\task.json", {"a": "9"})`.

## Writing recipes that last

- **Name windows by `exe:` or title, and keep numbers with `as`.** A window number changes every run; a number
  written in the file breaks the second time.
- **Target by `id=` first**, then `Type:Name`. `#paths` move when the layout changes, and names change with the
  program's language.
- **`wait` for anything that appears later** (a dialog, a window, a button that loads late) instead of `sleep`.
- **End with a `check`** on what the task was supposed to change. A recipe without one isn't finished.
- **Mix layers.** A `python` step can call the program's own API (COM, a CLI, a scripting console) and leave only the
  parts without an API to UIA. The cheapest layer that does each step wins.
- **When a recipe breaks, fix the file** from its report and run it again. Finishing the task by hand leaves the
  recipe stale for next time.
