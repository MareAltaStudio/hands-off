<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>hands-off demo overlay</title>
<style>
  @font-face { font-family: "Cascadia Mono"; src: local("Cascadia Mono"), local("Consolas"); }
  @font-face { font-family: "Inter"; src: local("Inter"), local("Segoe UI"); }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { width: 1920px; height: 1080px; background: #0f1115; overflow: hidden; }
  body { font-family: "Inter", "Segoe UI", sans-serif; color: #e8eaed; }
  #root { position: relative; width: 1920px; height: 1080px; background: #0f1115; overflow: hidden; }
  .scene { position: absolute; left: 0; top: 0; width: 1920px; height: 1080px; }
  .abs { position: absolute; }
  .mono { font-family: "Cascadia Mono", "Consolas", monospace; }

  /* title */
  #title-main { left: 0; width: 1920px; top: 410px; text-align: center; font-size: 150px; font-weight: 700; letter-spacing: -3px; }
  #title-sub { left: 0; width: 1920px; top: 600px; text-align: center; font-size: 46px; color: #e8eaed; opacity: 0; }
  #title-dot { left: 910px; top: 585px; width: 100px; height: 4px; background: #3ddc84; border-radius: 2px; }

  /* split */
  .label { top: 70px; width: 924px; font-size: 34px; font-weight: 600; letter-spacing: .2px; }
  #label-l { left: 24px; }
  #label-r { left: 972px; }
  .label i { display: inline-block; width: 12px; height: 12px; border-radius: 50%; background: #3ddc84; margin-right: 14px; vertical-align: 3px; }
  .panel { top: 140px; width: 924px; height: 520px; overflow: hidden; background: #1a1d23; border: 2px solid #2a2e36; border-radius: 6px; }
  #panel-l { left: 24px; }
  #panel-r { left: 972px; }
  .ph { position: absolute; left: 0; top: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 40px; color: #8a8f98; background: #1c1f26; }
  .vid { position: absolute; left: 0; top: 0; width: 1920px; height: 540px; transform-origin: 0 0; }
  #vid-l { transform: scale(0.9625); }
  #vid-r { transform: scale(0.9625) translateX(-960px); }
  #caption { left: 0; width: 1920px; top: 700px; text-align: center; font-size: 52px; font-weight: 600; opacity: 0; }
  #badge-wrap { left: 24px; top: 830px; width: 924px; height: 110px; }
  .badge { position: absolute; left: 0; top: 0; height: 110px; padding: 0 40px; display: flex; align-items: center; font-size: 44px; font-weight: 700; border-radius: 10px; border: 3px solid; }
  #badge-ok { color: #3ddc84; border-color: #3ddc84; background: rgba(61,220,132,.10); }
  #badge-bad { color: #ff5c5c; border-color: #ff5c5c; background: rgba(255,92,92,.12); opacity: 0; }
  #ticker { left: 972px; top: 830px; width: 924px; height: 150px; overflow: hidden; }
  .tk { position: absolute; left: 0; top: 0; width: 924px; font-size: 26px; white-space: nowrap; opacity: 0; color: #e8eaed; }
  .tk b { color: #3ddc84; font-weight: 400; margin-right: 12px; }

  /* end */
  #end-name { left: 0; width: 1920px; top: 300px; text-align: center; font-size: 80px; font-weight: 700; letter-spacing: -2px; }
  #end-cmd { left: 0; width: 1920px; top: 430px; text-align: center; font-size: 33px; color: #3ddc84; }
  #end-sub { left: 0; width: 1920px; top: 540px; text-align: center; font-size: 40px; color: #e8eaed; }
</style>
</head>
<body>
<div id="root" data-composition-id="root" data-width="1920" data-height="1080" data-start="0" data-duration="35" data-fps="30">

  <div id="s-title" class="scene clip" data-start="0" data-duration="3">
    <div id="title-main" class="abs">hands-off</div>
    <div id="title-dot" class="abs"></div>
    <div id="title-sub" class="abs">Your mouse stays yours.</div>
  </div>

  <div id="s-split" class="scene clip" data-start="3" data-duration="27">
    <div id="label-l" class="abs label"><i></i>You — real cursor</div>
    <div id="label-r" class="abs label"><i></i>Claude, through hands-off</div>
    <div id="panel-l" class="abs panel">__PANEL_L__</div>
    <div id="panel-r" class="abs panel">__PANEL_R__</div>
    <div id="caption" class="abs"></div>
    <div id="badge-wrap" class="abs">
      <div id="badge-ok" class="badge">Foreground: Blender ✓</div>
      <div id="badge-bad" class="badge"></div>
    </div>
    <div id="ticker" class="abs mono"></div>
  </div>

  <div id="s-end" class="scene clip" data-start="30" data-duration="5">
    <div id="end-name" class="abs">hands-off</div>
    <div id="end-cmd" class="abs mono">uvx --from git+https://github.com/MareAltaStudio/hands-off hands-off-mcp</div>
    <div id="end-sub" class="abs">Left side: a script moving the real cursor. One take, no cuts.</div>
  </div>

  <script src="node_modules/gsap/dist/gsap.min.js"></script>
  <script>
    const DATA = __DATA__;
    const OFF = 3;            // recording t=0 is composition t=3 s
    const Q = 0.2;            // quick, discreet entries (150-250 ms)
    const tl = gsap.timeline({ paused: true });

    // title 0-3
    tl.fromTo("#title-main", { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: Q }, 0.2);
    tl.fromTo("#title-sub", { opacity: 0, y: 14 }, { opacity: 1, y: 0, duration: Q }, 0.9);
    tl.to("#s-title", { opacity: 0, duration: Q }, 2.75);

    // split 3-30
    tl.fromTo("#s-split", { opacity: 0 }, { opacity: 1, duration: Q }, 3);
    tl.to("#s-split", { opacity: 0, duration: Q }, 29.75);

    // captions (about 8 s, 16 s, 24 s)
    [[8, "hands-off never touches your cursor."], [16, "Clicks go to the browser window, not through your mouse."], [24, "Your view keeps turning. The focus never left Blender."]]
      .forEach(([t, text]) => {
        tl.set("#caption", { textContent: text }, t - 0.01);
        tl.fromTo("#caption", { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: Q }, t);
        tl.to("#caption", { opacity: 0, duration: Q }, t + 4.5);
      });

    // focus badge: red whenever the latest sample has fg_is_paint false
    let bad = false;
    (DATA.focus_log || []).slice().sort((a, b) => a.t - b.t).forEach(s => {
      const isBad = !s.fg_is_paint;
      if (isBad) tl.set("#badge-bad", { textContent: "Foreground: " + s.fg_title + " ✗" }, OFF + s.t - 0.001);
      if (isBad !== bad) {
        tl.set("#badge-ok", { opacity: isBad ? 0 : 1 }, OFF + s.t);
        tl.set("#badge-bad", { opacity: isBad ? 1 : 0 }, OFF + s.t);
        bad = isBad;
      }
    });

    // ticker: last 3 actions, newest at the bottom; older ones move up and dim
    const acts = (DATA.ticker || []).slice().sort((a, b) => a.t - b.t);
    const tk = document.getElementById("ticker");
    const ROW = 50, OPA = [1, 0.72, 0.48];
    acts.forEach((a, i) => {
      const el = document.createElement("div");
      el.className = "tk"; el.id = "tk" + i;
      el.textContent = a.text;
      const mark = document.createElement("b");
      mark.textContent = ">";
      el.insertBefore(mark, el.firstChild);
      tk.appendChild(el);
      const pos = r => 100 - r * ROW;      // rank 0 (newest) at the bottom row
      tl.set(el, { y: pos(0) + 10, opacity: 0 }, OFF + a.t - 0.001);
      tl.to(el, { y: pos(0), opacity: OPA[0], duration: Q }, OFF + a.t);
      for (let r = 1; r <= 3; r++) {
        const nxt = acts[i + r];
        if (!nxt) break;
        tl.to(el, { y: pos(r), opacity: r <= 2 ? OPA[r] : 0, duration: Q }, OFF + nxt.t);
      }
    });

    // end card 30-35
    tl.fromTo("#s-end", { opacity: 0 }, { opacity: 1, duration: Q }, 30);
    tl.fromTo("#end-cmd", { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: Q }, 30.4);
    tl.fromTo("#end-sub", { opacity: 0, y: 10 }, { opacity: 1, y: 0, duration: Q }, 30.9);

    window.__timelines = window.__timelines || {};
    window.__timelines["root"] = tl;
  </script>
</div>
</body>
</html>
