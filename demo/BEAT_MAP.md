# Demo video: beat map

Goal: prove the one claim that matters, live and in one take: **while the agent works, the user's cursor, keyboard
and focus are untouched.**

Honesty rule: every pixel of the two screens is a real recording. Graphics only frame it (title, labels, captions
taken from the real logs). The "user" on the left is a script moving the **real** cursor, and the end card says so.

| Time | On screen | Source |
|---|---|---|
| before | Studio intro (3.1 s), dissolving into the title | made separately |
| 0–3 s | Title card: **hands-off** / "Your mouse stays yours." | HyperFrames |
| 3–30 s | Split screen. Left: monitor 1, Blender, the view orbited non-stop with the real cursor. Right: monitor 2, Claude reading the Blender manual in a guest Chrome window through hands-off. | one take: monitor 1 by ddagrab (NVENC), monitor 2 by gdigrab, cut from the same wall-clock instant |
| 3–30 s | Top labels: "You — real cursor" · "Claude, through hands-off" | HyperFrames |
| 3–30 s | Bottom-left badge, live: "Foreground: Blender ✓" (turns red if it ever changes) | `focus_log.jsonl` written by the user script |
| 3–30 s | Bottom-right ticker: the last 3 actions, e.g. `invoke · TabItem 'Pointers' · UIA SelectionItem` | hands-off `actions.log` |
| ~8 s | Caption: "hands-off never touches your cursor." | HyperFrames |
| ~16 s | Caption: "Clicks go to the browser window, not through your mouse." | HyperFrames |
| ~24 s | Caption: "Your view keeps turning. The focus never left Blender." | HyperFrames |
| 30–35 s | End card: `uvx --from git+https://github.com/MareAltaStudio/hands-off hands-off-mcp` · "Left side: a script moving the real cursor. One take, no cuts." | HyperFrames |

Deliverables: `demo.mp4` (1920×1080, H.264, for the release) and `demo.gif` (≤ 10 MB, for the README).

Style: dark neutral background `#0f1115`, text `#e8eaed`, one accent `#3ddc84` (OK states), red `#ff5c5c` only for a
failed state. Sans-serif (Inter, fallback Segoe UI). Entries quick and discreet (150–250 ms fade/slide). No emoji,
no spinning transitions, no sound.

Narration (Kokoro `af_heart` through Voicebox), placed by `narrate.py`: "This is hands-off." · "On the left, someone working in Blender: the real cursor, moved by a script." · "On the right, Claude is reading the Blender manual, clicking through a browser on the other screen." · "It never touches the mouse, the keyboard, or the focus. Blender stays in front the whole time." · "One take. No cuts." · "hands-off: an MCP server for Windows. Your mouse stays yours."
