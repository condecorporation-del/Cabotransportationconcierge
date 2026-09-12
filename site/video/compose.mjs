// Composes the hero promo from the generated scenes + a branded end card.
// Run: node video/compose.mjs            -> videos/hero-promo.mp4, .webm, poster
//      node video/compose.mjs --preview  -> video/preview-endcard.jpg (layout check only)
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..");
const FF = "C:/Users/conde/AppData/Local/Microsoft/WinGet/Packages/Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe/ffmpeg-8.1.1-full_build/bin/ffmpeg.exe";
const GEN = path.join(ROOT, "video", "gen");
const OUT = path.join(ROOT, "videos");
const preview = process.argv.includes("--preview");
fs.mkdirSync(OUT, { recursive: true });

const SCENES = ["01-this-september", "02-every-ride", "03-save-more", "04-ten-percent", "05-off"];
const TRANSITIONS = ["fadeblack", "smoothleft", "circleopen", "slideleft", "fade"];
const CLIP = 4, XF = 0.4, END_HOLD = 3.5;
const FONT = "C\\:/Windows/Fonts/ariblk.ttf";
const LEGAL_FONT = "C\\:/Windows/Fonts/segoeuib.ttf";
const legalFile = path.join(ROOT, "video", "legal.txt");
fs.writeFileSync(legalFile, "10% OFF THE TRANSFER RATE ON ALL SERVICES\nWITH TRAVEL DATES SEP 1-30, 2026.");
const esc = (p) => p.replace(/\\/g, "/").replace(/^([A-Za-z]):/, "$1\\:");

const norm = (i, label, extra = "") => `[${i}:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,setsar=1,trim=0:${CLIP},setpts=PTS-STARTPTS${extra},format=yuv420p[${label}]`;

// Gold 3D word: dark bronze extrusion layers + champagne face, fading and sliding in at `d` seconds.
function word(text, size, x, y, d) {
  const alpha = `'if(lt(t,${d}),0,if(lt(t,${d + 0.35}),(t-${d})/0.35,1))'`;
  const slide = (yy) => `'${yy}+if(lt(t,${d + 0.45}),(1-min(max(t-${d},0)/0.45,1))*70,0)'`;
  const layers = [];
  for (let k = 14; k >= 1; k--) {
    const shade = k > 9 ? "0x2E2210" : k > 4 ? "0x4A3818" : "0x6F5627";
    layers.push(`drawtext=fontfile='${FONT}':expansion=none:text='${text}':fontsize=${size}:fontcolor=${shade}:x=${x + k * 1.3}:y=${slide(y + k * 1.7)}:alpha=${alpha}`);
  }
  layers.push(`drawtext=fontfile='${FONT}':expansion=none:text='${text}':fontsize=${size}:fontcolor=0xE2BD6A:bordercolor=0xFFEBC0:borderw=2:x=${x}:y=${slide(y)}:alpha=${alpha}`);
  return layers.join(",");
}

const endLen = CLIP + END_HOLD;
const endcard = [
  `[5:v]scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080,fps=30,setsar=1,trim=0:${CLIP},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration=${END_HOLD}`,
  // right-side darkening is baked into 06-endcard.mp4 as a soft gradient
  word("SEPTEMBER", 90, 1200, 190, 0.5),
  word("10%", 285, 1195, 285, 0.9),
  word("OFF", 175, 1290, 590, 1.3),
  `drawtext=fontfile='${LEGAL_FONT}':expansion=none:textfile='${esc(legalFile)}':fontsize=30:line_spacing=10:fontcolor=white@0.9:x=110:y=965:alpha='if(lt(t,1.8),0,min((t-1.8)/0.5,1))'`,
  `format=yuv420p[endbase]`,
].join(",");
const logo = `[6:v]scale=250:250,format=rgba,fade=in:st=1.6:d=0.6:alpha=1[logo]`;
const endOverlay = `[endbase][logo]overlay=x=W-w-100:y=H-h-70:shortest=1,format=yuv420p[vend]`;

const inputs = [];
SCENES.forEach((s) => inputs.push("-i", path.join(GEN, `${s}.mp4`)));
inputs.push("-i", path.join(GEN, "06-endcard.mp4"));
inputs.push("-loop", "1", "-t", String(endLen), "-i", path.join(ROOT, "video", "logo-round.png"));

let graph, map, outArgs;
if (preview) {
  graph = [endcard, logo, endOverlay].join(";");
  map = "[vend]";
  outArgs = ["-ss", "3", "-frames:v", "1", path.join(ROOT, "video", "preview-endcard.jpg")];
} else {
  const parts = SCENES.map((s, i) => norm(i, `v${i}`));
  parts.push(endcard, logo, endOverlay);
  let prev = "v0", len = CLIP;
  const chain = [...SCENES.slice(1).map((s, i) => `v${i + 1}`), "vend"];
  chain.forEach((next, i) => {
    const offset = (len - XF).toFixed(2);
    const label = i === chain.length - 1 ? "vout" : `x${i}`;
    parts.push(`[${prev}][${next}]xfade=transition=${TRANSITIONS[i]}:duration=${XF}:offset=${offset}[${label}]`);
    len = len - XF + (next === "vend" ? endLen : CLIP);
    prev = label;
  });
  graph = parts.join(";");
  map = "[vout]";
  outArgs = ["-an", "-c:v", "libx264", "-preset", "slow", "-crf", "24", "-pix_fmt", "yuv420p", "-movflags", "+faststart", path.join(OUT, "hero-promo.mp4")];
  console.log(`Total length ≈ ${len.toFixed(1)}s`);
}

const run = (args) => {
  const r = spawnSync(FF, ["-v", "error", "-y", ...args], { stdio: "inherit" });
  if (r.status !== 0) process.exit(r.status || 1);
};
run([...inputs, "-filter_complex", graph, "-map", map, ...outArgs]);

if (!preview) {
  const mp4 = path.join(OUT, "hero-promo.mp4");
  run(["-i", mp4, "-c:v", "libvpx-vp9", "-crf", "36", "-b:v", "0", "-row-mt", "1", "-deadline", "good", "-cpu-used", "2", "-an", path.join(OUT, "hero-promo.webm")]);
  run(["-sseof", "-2", "-i", mp4, "-frames:v", "1", "-q:v", "3", path.join(OUT, "hero-promo-poster.jpg")]);
  for (const f of ["hero-promo.mp4", "hero-promo.webm", "hero-promo-poster.jpg"]) {
    console.log(f, (fs.statSync(path.join(OUT, f)).size / 1048576).toFixed(2) + " MB");
  }
}
