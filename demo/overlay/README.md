# hands-off demo overlay (HyperFrames)

Graphics for the demo video, specified in `../BEAT_MAP.md`: title, labels, captions, focus badge, action ticker, end card.
1920x1080, 35 s, 30 fps. The two screens come from the real recording (`../out/split.mp4`).

## After the real recording (one command)

    cd demo/overlay
    npm install          # first time only
    node render.mjs

It builds `index.html`, renders with HyperFrames, and writes `../out/demo.mp4` (H.264, yuv420p, faststart) and
`../out/demo.gif` (960 px / 15 fps, shrunk automatically until it is <= 10 MB; the settings used are printed).

Inputs (defaults): `../out/split.mp4` and `../out/data.json`, both written by `../run_demo.py`.
Override with `node render.mjs --split X.mp4 --data Y.json --out DIR`.

- `split.mp4`: 1920x540, side by side. Left half = monitor 1 (user), right half = monitor 2 (agent). Each half fills a
  16:9 panel. Recording t=0 plays at composition t=3 s; up to 27 s are shown.
- `data.json`: `{"focus": [{t, fg_title, fg_is_paint}], "ticker": [{t, tool, text}]}`. The badge turns red
  ("Foreground: <title> ✗") from a sample with `fg_is_paint: false` until the next sample with true. Ticker lines become
  `<tool> · <target> · <layer>` (from `clicked (UIA Invoke): #1.2.3 Button 'Four'`); other texts become
  `<tool> · <text>` cut at 60 characters. `t` is seconds since the recording start (composition time = 3 + t).

## Requirements

- Node >= 22, local Chrome, `uv` (render.mjs gets ffmpeg from `imageio-ffmpeg` through `uvx`).
- ffprobe (HyperFrames needs it; imageio-ffmpeg does not ship one): on PATH, or set `HYPERFRAMES_FFPROBE_PATH`.
  If missing, render.mjs stops with a message. `winget install --id Gyan.FFmpeg -e` provides it.
- `HYPERFRAMES_FFMPEG_PATH` overrides the ffmpeg lookup.

## Other

    node build.mjs                                   # placeholders + data.sample.json -> index.html
    node build.mjs --split ../out/split.mp4 --data ../out/data.json
    npx hyperframes snapshot . --at 1.5,9,20,33 --no-end   # still frames

`index.html` and `recording.mp4` are generated; edit `template.tpl` (layout, timings, texts) and `build.mjs`.
Fake test inputs: `../out/fake_split.mp4`, `../out/fake_data.json`.
