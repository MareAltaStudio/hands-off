"""Recipes: a task the agent figured out once, frozen into steps that run without it.

Exploring a program costs an agent many turns: list the windows, read the tree,
try a target, check. Once the path is known, none of that judgement is needed
again - the same clicks, the same text, the same checks. A recipe is that path
written down as JSON, and it runs in one call (the `run_recipe` tool) or with
no agent at all (`hands-off-mcp run recipe.json name=value`).

    {
      "name": "add two numbers in Calculator",
      "vars": {"a": "7", "b": "5"},
      "steps": [
        {"do": "launch", "command": "calc.exe", "as": "calc"},
        {"do": "wait", "window": "exe:CalculatorApp.exe", "as": "calc"},
        {"do": "invoke", "window": "${calc}", "target": "id=num${a}Button"},
        {"do": "invoke", "window": "${calc}", "target": "id=plusButton"},
        {"do": "invoke", "window": "${calc}", "target": "id=num${b}Button"},
        {"do": "invoke", "window": "${calc}", "target": "id=equalButton"},
        {"do": "check", "window": "${calc}", "target": "id=CalculatorResults", "contains": "12"},
        {"do": "close", "window": "${calc}"}
      ]
    }

Every tool of the server is a step (`do` = its name, the other keys = its
arguments), plus:

    wait    until a window (and optionally a `target` inside it) exists;
            "as" keeps the window number for later steps
    check   read() a control and require `contains`, `equals` or `matches`
            (a regex) in what it says - the recipe's proof, the step that
            makes it safe to run unattended. Prefer `matches` with anchors:
            "contains 2" passes on "12"
    sleep   {"s": 0.5}
    python  run a script with this interpreter; `script` relative to the
            recipe file, `args` a list; non-zero exit stops the recipe

`${name}` is replaced from `vars`, the caller's values and every "as". A
window number changes between runs, so a recipe names windows by `exe:` or
title and keeps the number with "as" - never a number written in the file.

The recipe stops at the first step that answers "[error]" or fails a check,
and the report says which step and why. A "finally" list of steps (same
format) runs afterwards either way - close what the recipe opened, so a
failed run doesn't leave windows behind. A recipe that can't prove its
result with a check is not finished.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from pathlib import Path

from hands_off import server as S

_VAR = re.compile(r"\$\{(\w+)\}")
_WINDOW_NO = re.compile(r"^window (\d+)")


def _subst(value, env: dict):
    if isinstance(value, str):
        def rep(m):
            if m.group(1) not in env:
                raise KeyError(f"${{{m.group(1)}}} is not defined")
            return str(env[m.group(1)])
        return _VAR.sub(rep, value)
    if isinstance(value, list):
        return [_subst(v, env) for v in value]
    if isinstance(value, dict):
        return {k: _subst(v, env) for k, v in value.items()}
    return value


def _wait(args: dict) -> tuple[bool, str, int | None]:
    deadline = time.time() + float(args.get("timeout", 15))
    target = args.get("target", "")
    last = ""
    while time.time() < deadline:
        h = S._resolve(args["window"])
        if isinstance(h, int):
            if not target:
                return True, f"window {h} is there", h
            r = S.read(str(h), target)
            if not r.startswith("[error]"):
                return True, f"window {h}: {r.splitlines()[0]}", h
            last = r
        else:
            last = h
        time.sleep(0.25)
    return False, f"[error] waited {args.get('timeout', 15)}s: {last}", None


def _check(args: dict) -> tuple[bool, str]:
    r = S.read(args["window"], args["target"])
    if r.startswith("[error]"):
        return False, r
    # Only what the control SAYS counts - never its rectangle: "99" must not
    # pass because the control ends at y=199.
    lines = r.splitlines()
    said = [lines[0]] + [ln for ln in lines[1:]
                         if ln.startswith(("value: ", "text: ", "checked: ", "expanded: ", "selected: "))]
    if "equals" in args:
        vals = [ln.split(": ", 1)[1].strip("'\"") for ln in said[1:]]
        m = re.match(r"^#\S+ \S+ '(.*)'$", said[0])
        vals += [m.group(1)] if m else []
        ok = str(args["equals"]) in vals
        return ok, f"{'ok' if ok else '[error] check failed'}: wanted exactly {args['equals']!r} in {vals}"
    if "matches" in args:
        ok = any(re.search(str(args["matches"]), ln) for ln in said)
        return ok, f"{'ok' if ok else '[error] check failed'}: wanted /{args['matches']}/ in:\n" + "\n".join(said)
    want = str(args.get("contains", ""))
    ok = any(want in ln for ln in said)
    return ok, f"{'ok' if ok else '[error] check failed'}: wanted {want!r} in:\n" + "\n".join(said)


def _python(args: dict, base: Path) -> tuple[bool, str]:
    script = Path(args["script"])
    if not script.is_absolute():
        script = base / script
    p = subprocess.run([sys.executable, str(script), *map(str, args.get("args", []))],
                       capture_output=True, text=True, timeout=float(args.get("timeout", 300)))
    out = (p.stdout + p.stderr).strip()
    return p.returncode == 0, f"exit {p.returncode}" + (f"\n{out[-1500:]}" if out else "")


_TOOLS = {fn.__name__: fn for fn in S.READ_ONLY + S.ACTING}


def run(recipe: dict | str, values: dict | None = None, base: Path | None = None) -> tuple[bool, str]:
    """Run a recipe (a dict, a JSON string or a path). Returns (ok, report)."""
    if isinstance(recipe, str):
        p = Path(recipe)
        if not recipe.lstrip().startswith("{") and p.is_file():
            base = base or p.resolve().parent
            recipe = json.loads(p.read_text(encoding="utf-8"))
        else:
            recipe = json.loads(recipe)
    base = base or Path.cwd()
    env = {**recipe.get("vars", {}), **(values or {})}
    steps = recipe.get("steps", [])
    lines = [f"recipe {recipe.get('name', '?')!r}: {len(steps)} steps"]
    t0 = time.time()
    ok = _run_steps(steps, env, base, lines, stop_on_error=True)
    lines.append(f"{'done' if ok else 'failed'} in {time.time() - t0:.1f}s.")
    if recipe.get("finally"):
        lines.append("finally:")
        _run_steps(recipe["finally"], env, base, lines, stop_on_error=False)
    return ok, "\n".join(lines)


def _run_steps(steps: list, env: dict, base: Path, lines: list, stop_on_error: bool) -> bool:
    all_ok = True
    for i, raw in enumerate(steps, 1):
        try:
            step = _subst(dict(raw), env)
        except KeyError as exc:
            lines.append(f"{i:>2}. [error] {exc}")
            if stop_on_error:
                return False
            all_ok = False
            continue
        do = step.pop("do", "")
        keep = step.pop("as", None)
        note = step.pop("note", "")
        try:
            if do == "wait":
                ok, msg, h = _wait(step)
                if ok and keep:
                    env[keep] = h
            elif do == "check":
                ok, msg = _check(step)
            elif do == "sleep":
                time.sleep(float(step.get("s", 0.5)))
                ok, msg = True, f"slept {step.get('s', 0.5)}s"
            elif do == "python":
                ok, msg = _python(step, base)
            elif do in _TOOLS:
                out = _TOOLS[do](**step)
                msg = out[0] if isinstance(out, list) else str(out)
                ok = not msg.startswith("[error]") and "could NOT give it back" not in msg
                if keep:  # even on failure: "finally" must be able to close it
                    m = _WINDOW_NO.match(msg)
                    if m:
                        env[keep] = int(m.group(1))
            else:
                ok, msg = False, f"[error] unknown step {do!r}"
        except Exception as exc:  # noqa: BLE001 - a step failing is a report, not a crash
            ok, msg = False, f"[error] {type(exc).__name__}: {exc}"
        label = f"{do}" + (f" ({note})" if note else "")
        lines.append(f"{i:>2}. {label}: {msg}")
        if not ok:
            all_ok = False
            if stop_on_error:
                lines.append(f"stopped at step {i}.")
                return False
    return all_ok


def run_recipe(recipe: str, values: dict | None = None) -> str:
    """Run a recipe: a task already figured out, frozen as steps (clicks,
    text, waits, checks, Python scripts) that run in one call instead of one
    agent turn each. `recipe` = path to a .json file or the JSON itself;
    `values` fills its ${variables}. Stops at the first error or failed check
    and says which step. See the module docstring for the format."""
    ok, report = run(recipe, values)
    return ("ok\n" if ok else "[error] recipe failed\n") + report


def main_cli(argv: list[str]) -> int:
    if not argv:
        print("usage: hands-off-mcp run recipe.json [name=value ...]")
        return 2
    values = dict(a.split("=", 1) for a in argv[1:] if "=" in a)
    ok, report = run(argv[0], values)
    print(report)
    return 0 if ok else 1
