// Generates index.html from template.tpl + data JSON + (optional) the real recording.
// Usage: node build.mjs [--split ../out/split.mp4] [--data ../out/data.json]
//   no arguments = placeholders + data.sample.json
// split.mp4 is 1920x540, side by side: left half = monitor 1 (user), right half = monitor 2 (agent).
// data.json = {"focus": [{t, fg_title, fg_is_paint}], "ticker": [{t, tool, text}]}  ("focus_log" also accepted)
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf("--" + k); return i >= 0 ? args[i + 1] : d; };
const here = path.dirname(fileURLToPath(import.meta.url));
const dataPath = path.resolve(opt("data", path.join(here, "data.sample.json")));
const data = JSON.parse(fs.readFileSync(dataPath, "utf8"));
data.focus_log = data.focus_log || data.focus || [];
delete data.focus;

// "clicked (UIA Invoke): #1.2.1.7.4 Button 'Four'" -> "invoke · Button 'Four' · UIA Invoke"
function fmt(a) {
  if (!a.tool) return a.text;
  const m = /\(([^)]*)\):\s*(?:#[\d.]+\s*)?(.+)$/.exec(a.text || "");
  if (m) return `${a.tool} · ${m[2]} · ${m[1]}`;
  const s = `${a.tool} · ${a.text || ""}`;
  return s.length > 60 ? s.slice(0, 59) + "…" : s;
}
data.ticker = (data.ticker || []).map(a => ({ t: a.t, text: fmt(a) }));

const split = opt("split");
let L, R;
if (split) {
  // copied next to index.html so the renderer can reach it
  fs.copyFileSync(path.resolve(split), path.join(here, "recording.mp4"));
  const v = id => `<video id="${id}" class="vid" src="recording.mp4" data-start="3" data-duration="27" muted playsinline></video>`;
  L = v("vid-l"); R = v("vid-r");
} else {
  L = '<div class="ph">monitor 1 recording</div>';
  R = '<div class="ph">monitor 2 recording</div>';
}
let html = fs.readFileSync(path.join(here, "template.tpl"), "utf8");
html = html.replace("__PANEL_L__", () => L).replace("__PANEL_R__", () => R).replace("__DATA__", () => JSON.stringify(data));
fs.writeFileSync(path.join(here, "index.html"), html);
console.log("index.html written (split: " + (split || "placeholders") + ", data: " + dataPath + ")");
