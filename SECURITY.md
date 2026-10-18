# Security

hands-off operates real programs with the rights of the user who runs it. Treat it like giving someone your
keyboard: it can press "Delete", confirm a dialog or close unsaved work.

## Recommendations

- Keep the acting tools behind your MCP client's permission prompt until you trust the flow. The four read-only tools
  are marked `readOnlyHint` so they can be allowed separately.
- Recipes with `python` steps run code. Only run recipes you wrote or have read.
- Text read from windows (`tree`, `read`, `capture`) is data from other programs. An agent should never follow
  instructions found there.
- The action log (`%LOCALAPPDATA%\hands-off\actions.log`) records every acting call; read it when something
  surprises you.

## Reporting a vulnerability

Please don't open a public issue. Use GitHub's private vulnerability reporting on this repository
(**Security → Report a vulnerability**). You'll get an answer within a week.
