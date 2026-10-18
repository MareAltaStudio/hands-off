"""Recipe engine tests that need no window: the tools are replaced by fakes.

The real thing (UIA against Calculator) is `hands-off-mcp run recipes/calculator_add.json`,
which needs a desktop session - see CONTRIBUTING.md.
"""

from __future__ import annotations

import json
import sys

import pytest

from hands_off import recipes
from hands_off import server as S


@pytest.fixture
def fake(monkeypatch):
    """Fake tools that record calls; `read` answers what the test puts in `display`."""
    calls: list[tuple[str, dict]] = []
    state = {"display": "Display is 12", "next_window": 4242}

    def tool(name, answer):
        def fn(**kw):
            calls.append((name, kw))
            return answer(kw) if callable(answer) else answer
        fn.__name__ = name
        return fn

    tools = {
        "launch": tool("launch", lambda kw: f"window {state['next_window']} app.exe 'App'"),
        "invoke": tool("invoke", "clicked (UIA Invoke): #1 Button 'X'"),
        "close": tool("close", "close request sent."),
        "fails": tool("fails", "[error] nothing matches 'Nope'; see tree()"),
        "steals": tool("steals", "ok\n[guard] the program stole the focus and I could NOT give it back"),
    }
    monkeypatch.setattr(recipes, "_TOOLS", tools)
    monkeypatch.setattr(S, "read", lambda window, target: (
        f"#1.2 Text '{state['display']}'\nrect: (10, 120, 400, 199)\nenabled: True"))
    monkeypatch.setattr(S, "_resolve", lambda window: int(window) if str(window).isdigit() else "[error] no")
    return calls, state


def steps(*s, fin=None, vars=None):
    r = {"name": "t", "vars": vars or {}, "steps": list(s)}
    if fin:
        r["finally"] = fin
    return r


def test_variables_and_as(fake):
    calls, _ = fake
    ok, report = recipes.run(steps(
        {"do": "launch", "command": "app.exe", "as": "w"},
        {"do": "invoke", "window": "${w}", "target": "id=num${a}Button"},
        vars={"a": "7"}), {"a": "9"})
    assert ok, report
    assert calls[1] == ("invoke", {"window": "4242", "target": "id=num9Button"})


def test_undefined_variable_stops(fake):
    ok, report = recipes.run(steps({"do": "invoke", "window": "${missing}", "target": "x"}))
    assert not ok and "${missing} is not defined" in report


def test_error_stops_and_finally_runs(fake):
    calls, _ = fake
    ok, report = recipes.run(steps(
        {"do": "launch", "command": "app.exe", "as": "w"},
        {"do": "fails"},
        {"do": "invoke", "window": "${w}", "target": "never"},
        fin=[{"do": "close", "window": "${w}"}]))
    assert not ok
    assert [c[0] for c in calls] == ["launch", "fails", "close"]
    assert "stopped at step 2" in report and "finally:" in report


def test_focus_not_returned_fails_but_keeps_window(fake):
    calls, _ = fake

    def launch(**kw):
        calls.append(("launch", kw))
        return "window 77 app.exe 'App'; the program stole the focus and I could NOT give it back"

    recipes._TOOLS["launch"] = launch
    ok, _ = recipes.run(steps({"do": "launch", "command": "app.exe", "as": "w"},
                              fin=[{"do": "close", "window": "${w}"}]))
    assert not ok
    assert calls[-1] == ("close", {"window": "77"})


@pytest.mark.parametrize("check, passes", [
    ({"contains": "12"}, True),
    ({"contains": "2"}, True),            # the trap the docs warn about
    ({"contains": "99"}, False),          # 199 is in the rect, which must not count
    ({"matches": " 12'$"}, True),
    ({"matches": " 2'$"}, False),
    ({"equals": "Display is 12"}, True),
    ({"equals": "12"}, False),
])
def test_check(fake, check, passes):
    ok, _ = recipes.run(steps({"do": "check", "window": "1", "target": "id=r", **check}))
    assert ok is passes


def test_wait_finds_window_and_keeps_number(fake):
    calls, _ = fake
    ok, report = recipes.run(steps(
        {"do": "wait", "window": "4242", "timeout": 1, "as": "w"},
        {"do": "invoke", "window": "${w}", "target": "x"}))
    assert ok, report
    assert calls[0] == ("invoke", {"window": "4242", "target": "x"})


def test_wait_times_out(fake):
    ok, report = recipes.run(steps({"do": "wait", "window": "Nope", "timeout": 0.3}))
    assert not ok and "waited" in report


def test_python_step(fake, tmp_path):
    (tmp_path / "ok.py").write_text("import sys; print('hi', sys.argv[1])")
    (tmp_path / "bad.py").write_text("raise SystemExit(3)")
    ok, report = recipes.run(steps({"do": "python", "script": "ok.py", "args": ["there"]}), base=tmp_path)
    assert ok and "hi there" in report
    ok, report = recipes.run(steps({"do": "python", "script": "bad.py"}), base=tmp_path)
    assert not ok and "exit 3" in report


def test_unknown_step(fake):
    ok, report = recipes.run(steps({"do": "teleport"}))
    assert not ok and "unknown step 'teleport'" in report


def test_recipe_from_file_and_cli(fake, tmp_path, capsys):
    f = tmp_path / "r.json"
    f.write_text(json.dumps(steps({"do": "check", "window": "1", "target": "x", "matches": " ${n}'$"},
                                  vars={"n": "12"})))
    assert recipes.main_cli([str(f)]) == 0
    assert recipes.main_cli([str(f), "n=13"]) == 1
    assert recipes.main_cli([]) == 2
    capsys.readouterr()


def test_example_recipes_are_valid_json():
    from pathlib import Path

    for p in (Path(__file__).parents[1] / "recipes").glob("*.json"):
        r = json.loads(p.read_text(encoding="utf-8"))
        assert r["steps"] and all("do" in s for s in r["steps"] + r.get("finally", [])), p


def test_server_registers_every_tool():
    names = {fn.__name__ for fn in S.READ_ONLY + S.ACTING}
    assert names == {"list_windows", "tree", "read", "capture", "invoke", "type_text", "keys",
                     "click_xy", "menu", "move", "launch", "close"}
    assert sys.platform == "win32"
