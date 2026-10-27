# How the demo video is made

Everything here is in the open so anyone can check the video isn't staged.

**The take.** One take, no cuts. On monitor 1 a script plays the user, orbiting a Blender scene with the
**real** cursor. On monitor 2 Claude, through hands-off, reads the Blender manual in a guest Chrome window.
Over the 30-second take the foreground window was sampled every 100 ms and stayed on Blender every time
(301 of 301 samples).

| File | What it does |
|---|---|
| `run_demo.py` | Records the take: opens the programs, starts the capture, the user script and the recipe, then cuts both monitors side by side. `--user-app blender --apps chrome --recipe demo_browse.json` is the published take. |
| `fake_user.py` | The user. It moves the **real** cursor with `SendInput`, the only synthetic input in this repository, and it's the user's input, not the agent's. It stops on Esc or if someone else moves the mouse, and logs the foreground window every 100 ms (`out/focus_log.jsonl`). |
| `demo_browse.json` | The recipe hands-off runs: four `click_xy` on the manual page, found one step at a time with `probe_step.py`. |
| `demo_actions.json` | An earlier take: Mouse Properties and Character Map (classic Win32 windows). |
| `make_scene.py` | Builds the Blender scene (`blender --background --factory-startup --python make_scene.py -- out/scene.blend`). |
| `backdrop.py`, `clear_screen.py` | Keep anything else off both screens during the take. |
| `launch_focus_test.py`, `browser_probe.py` | Measurements behind [focus on launch](../docs/compatibility.md#focus-on-launch). |
| `overlay/` | Title, labels, captions, focus badge and action ticker, with [HyperFrames](https://www.npmjs.com/package/hyperframes). The badge and the ticker come from the take's own logs (`ticker_from_recipe.py`). |
| `narrate.py`, `voicebox_api.py` | The narration: a local [Voicebox](https://github.com/jamiepine/voicebox) with the Kokoro voice `af_heart`. |

**Capture.** Monitor 1 through Desktop Duplication (`ddagrab`, encoded on the GPU with NVENC: on the CPU, with
Blender running, it dropped to 18 fps). Monitor 2 through `gdigrab`. Both are stamped with the wall clock and
cut from the same instant.

**Not in this folder.** The studio intro and the music were made separately: the music in REAPER with VSCO 2
Community Edition samples (CC0), a piano for the user's hand and a glockenspiel note on each of Claude's clicks.

To record: close or pause anything that may open windows, don't touch the mouse, then run
`python demo/run_demo.py --user-app blender --apps chrome --recipe demo/demo_browse.json --seconds 30`.
Esc stops the user script.
