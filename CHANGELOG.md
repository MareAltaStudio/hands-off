# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-10-18

### Added
- MCP server with 12 tools: `list_windows`, `tree`, `read`, `capture` (read-only) and `invoke`, `type_text`,
  `keys`, `click_xy`, `menu`, `move`, `launch`, `close`.
- UI Automation first, window messages second, never synthetic input.
- Focus guard that hands the foreground back when the target program takes it, judging by the final state and
  falling back to `SwitchToThisWindow` when `SetForegroundWindow` is refused.
- Capture of covered and GPU-rendered windows (`PrintWindow` with `PW_RENDERFULLCONTENT`, Windows Graphics
  Capture fallback).
- Recipes: tasks frozen as JSON (`wait`, `check`, `sleep`, `python` steps, variables, `finally`), run through
  `run_recipe` or `hands-off-mcp run`.
- `corner` option on `move` and `launch`.
- Agent skill (`skills/hands-off/SKILL.md`).
- Action log at `%LOCALAPPDATA%\hands-off\actions.log`.
