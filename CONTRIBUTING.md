# Contributing

Thanks for helping. hands-off is small on purpose; the bar for a change is that it keeps the one rule:
**never touch the user's mouse, keyboard or focus.** A pull request that adds a `SendInput` fallback, however
convenient, won't be merged.

## Setup

```powershell
git clone https://github.com/MareAltaStudio/hands-off
cd hands-off
uv venv
uv pip install -e ".[dev]"
```

## Tests

```powershell
.venv\Scripts\python -m pytest            # recipe engine, no windows needed (this runs in CI)
.venv\Scripts\hands-off-mcp --selftest     # read-only tools against your desktop
.venv\Scripts\hands-off-mcp run recipes\calculator_add.json   # end to end: opens Calculator, adds, checks, closes
```

The end-to-end recipe needs an interactive desktop session, so CI can't run it. Run it before opening a pull request
that touches `server.py`, and say in the PR that you did.

## What helps most

- **Compatibility reports.** A program you drove (or couldn't), its version, and what worked. Measured results go
  into [docs/compatibility.md](docs/compatibility.md).
- **Traps.** Something that failed silently and why. Each one becomes a line in the skill and a comment in the code,
  next to the line it explains.
- **Example recipes** for common tasks, with a `check` at the end.

## Style

- Failures are returned as text starting with `[error]`, never raised: the agent has to read them.
- Every acting result says which layer did the work (UIA pattern or which message).
- A comment explains *why*, with the measurement when there is one.
- `ruff check` and `pyflakes` should be clean.
