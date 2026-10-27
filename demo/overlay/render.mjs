// One command after the real recording:  node render.mjs
//   build -> HyperFrames render (1920x1080, 60 fps) -> ../out/demo.mp4 (H.264, yuv420p, faststart) -> ../out/demo.gif (<= 10 MB)
// Options: --split <mp4> --data <json> --out <dir>   (defaults: ../out/split.mp4, ../out/data.json, ../out)
import { execFileSync, spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const args = process.argv.slice(2);
const opt = (k, d) => { const i = args.indexOf("--" + k); return i >= 0 ? path.resolve(args[i + 1]) : d; };
const outDir = opt("out", path.resolve(here, "../out"));
const split = opt("split", path.join(outDir, "split.mp4"));
const data = opt("data", path.join(outDir, "data.json"));
const die = m => { console.error("ERROR: " + m); process.exit(1); };

// ffmpeg: from imageio-ffmpeg through uvx
let ffmpeg = process.env.HYPERFRAMES_FFMPEG_PATH;
if (!ffmpeg) {
  try {
    ffmpeg = execFileSync("uvx", ["--from", "imageio-ffmpeg", "python", "-c",
      "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"], { encoding: "utf8" }).trim().split(/\r?\n/).pop();
  } catch (e) { die("could not get ffmpeg via uvx (imageio-ffmpeg). Install uv, or set HYPERFRAMES_FFMPEG_PATH."); }
}
if (!fs.existsSync(ffmpeg)) die("ffmpeg not found at " + ffmpeg);

// ffprobe: env var, else PATH
let ffprobe = process.env.HYPERFRAMES_FFPROBE_PATH;
if (!ffprobe) {
  const w = spawnSync(process.platform === "win32" ? "where" : "which", ["ffprobe"], { encoding: "utf8" });
  if (w.status === 0) ffprobe = w.stdout.trim().split(/\r?\n/)[0];
}
if (!ffprobe || !fs.existsSync(ffprobe)) die(
  "ffprobe not found (HyperFrames needs it; imageio-ffmpeg does not ship it). Install FFmpeg (winget install --id Gyan.FFmpeg -e) " +
  "so ffprobe is on PATH, or set HYPERFRAMES_FFPROBE_PATH to a ffprobe.exe.");

const env = { ...process.env, HYPERFRAMES_FFMPEG_PATH: ffmpeg, HYPERFRAMES_FFPROBE_PATH: ffprobe };
const run = (cmd, a, o = {}) => {
  const r = spawnSync(cmd, a, { stdio: "inherit", env, cwd: here, shell: cmd === "npx", ...o });
  if (r.status !== 0) die(`${cmd} ${a.slice(0, 3).join(" ")} failed (exit ${r.status})`);
};
const t0 = Date.now();
fs.mkdirSync(outDir, { recursive: true });

run("node", ["build.mjs", "--split", split, "--data", data]);
const raw = path.join(outDir, "demo_raw.mp4");
run("npx", ["hyperframes", "render", "-q", "standard", "-f", "60", "-o", raw]);
const t1 = Date.now();

const mp4 = path.join(outDir, "demo.mp4");
run(ffmpeg, ["-y", "-loglevel", "error", "-i", raw, "-c:v", "libx264", "-crf", "18", "-preset", "slow",
  "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-an", mp4]);
fs.rmSync(raw, { force: true });

// GIF: 960 px, 15 fps; shrink until <= 10 MB
const gif = path.join(outDir, "demo.gif");
let used = "";
for (const [w, fps] of [[960, 15], [960, 12], [800, 12], [800, 10], [640, 10], [640, 8]]) {
  const vf = `fps=${fps},scale=${w}:-1:flags=lanczos,split[a][b];[a]palettegen=max_colors=128[p];[b][p]paletteuse=dither=bayer:bayer_scale=4`;
  run(ffmpeg, ["-y", "-loglevel", "error", "-i", mp4, "-filter_complex", vf, "-loop", "0", gif]);
  const mb = fs.statSync(gif).size / 1048576;
  used = `${w}px, ${fps} fps, ${mb.toFixed(2)} MB`;
  if (mb <= 10) break;
  console.log(`GIF ${used} is over 10 MB, shrinking...`);
}
const sec = s => ((s) / 1000).toFixed(0);
console.log(`done: ${mp4}\n      ${gif} (${used})\nrender ${sec(t1 - t0)} s, total ${sec(Date.now() - t0)} s`);
