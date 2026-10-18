# Example recipes

| Recipe | What it shows |
|---|---|
| [calculator_add.json](calculator_add.json) | `launch` with `as`, `wait` for a control, `invoke` by `id=`, a `matches` check, `finally` cleanup, variables from the command line |

```powershell
hands-off-mcp run recipes/calculator_add.json             # 7 + 5 = 12
hands-off-mcp run recipes/calculator_add.json a=9 b=4 sum=13
```

The format is documented in [docs/recipes.md](../docs/recipes.md). New examples are welcome: keep them to programs
that ship with Windows, and end them with a `check`.
