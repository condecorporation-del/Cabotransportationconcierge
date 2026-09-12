// Generates the hero promo scenes with OpenRouter video API (alibaba/wan-3.0-prime).
// Run: node video/generate.mjs [sceneId ...]   (no args = all scenes)
import fs from "node:fs";
import path from "node:path";

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, "$1")), "..");
const KEY = process.env.OPENROUTER_API_KEY;
if (!KEY) throw new Error("OPENROUTER_API_KEY no está definida (ver AGENTS.md §7).");
const API = "https://openrouter.ai/api/v1";
const MODEL = "alibaba/wan-3.0-prime";
const OUT = path.join(ROOT, "video", "gen");
fs.mkdirSync(OUT, { recursive: true });

const SUV = "a glossy black 2025 Chevrolet Suburban full-size luxury SUV with chrome grille, gold Chevrolet bowtie emblem and bright LED headlights";
const LETTERS = (word) => `giant 3D extruded block letters made of polished champagne-gold metal with dark bronze beveled sides, bold heavy sans-serif font, spelling exactly "${word}", perfectly spelled, standing in the scene`;
const STYLE = "Cinematic luxury car commercial, photorealistic, 16:9, smooth slow dolly camera move, rich contrast, shallow depth of field, high detail. No other text, no logos, no watermark, no subtitles.";

const SCENES = [
  { id: "01-this-september", prompt: `${STYLE} Night at the modern Los Cabos international airport terminal entrance with warm lights and palm trees, wet reflective pavement. ${LETTERS("THIS SEPTEMBER")} on the left side. On the right, ${SUV} rolls slowly toward the camera.` },
  { id: "02-every-ride", prompt: `${STYLE} Sunrise on a winding coastal highway in Baja California, Sea of Cortez on the left, desert hills and cacti on the right. ${LETTERS("EVERY RIDE")} floating in the sky above the road. ${SUV} drives toward the camera in the center lane.` },
  { id: "03-save-more", prompt: `${STYLE} Dusk at a luxury Mexican resort entrance with palm trees, warm uplights and stone paving. A black Mercedes-Benz Sprinter luxury van parked on the left with headlights on. ${LETTERS("SAVE MORE")} on the right side.` },
  { id: "04-ten-percent", prompt: `${STYLE} Golden sunset on a quiet Cabo San Lucas beach with gentle waves and a dramatic orange sky. Enormous ${LETTERS("10%")} rising from the sand filling the frame. ${SUV} parked in front of the letters, camera slowly pushing in.` },
  { id: "05-off", prompt: `${STYLE} Night at Cabo San Lucas marina with lit luxury yachts and the rocky El Arco silhouette in the distance, wet reflective dock. ${LETTERS("OFF")} glowing softly on the left with reflections. ${SUV} parked on the right, headlights on.` },
  { id: "06-endcard", prompt: `${STYLE} Blue-hour dusk at a boutique hotel driveway in Cabo San Lucas with palm silhouettes and warm lights. ${SUV} parked in the left third of the frame angled toward camera, headlights on. The right half of the frame is clean dark sky and soft background with empty space. Very slow push-in. Absolutely no text or letters anywhere.` },
];

const headers = { Authorization: `Bearer ${KEY}`, "Content-Type": "application/json", "X-Title": "Cabo Transportation Concierge" };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const only = process.argv.slice(2);
const todo = SCENES.filter((s) => !only.length || only.includes(s.id));

async function run(scene) {
  const body = { model: MODEL, prompt: scene.prompt, duration: 4, resolution: "1080p", aspect_ratio: "16:9", generate_audio: false, seed: 2026 };
  const res = await fetch(`${API}/videos`, { method: "POST", headers, body: JSON.stringify(body) });
  const job = await res.json();
  if (!res.ok || !job.id) throw new Error(`${scene.id} submit failed ${res.status}: ${JSON.stringify(job).slice(0, 400)}`);
  console.log(`[${scene.id}] submitted ${job.id}`);
  const pollUrl = job.polling_url || `${API}/videos/${job.id}`;
  const t0 = Date.now();
  for (;;) {
    await sleep(8000);
    const p = await (await fetch(pollUrl, { headers })).json();
    if (p.status === "completed") {
      const v = await fetch(`${API}/videos/${job.id}/content?index=0`, { headers });
      if (!v.ok) throw new Error(`${scene.id} download failed ${v.status}`);
      const file = path.join(OUT, `${scene.id}.mp4`);
      fs.writeFileSync(file, Buffer.from(await v.arrayBuffer()));
      console.log(`[${scene.id}] done in ${Math.round((Date.now() - t0) / 1000)}s, cost $${p.usage?.cost ?? "?"} -> ${file}`);
      return { id: scene.id, job: job.id, cost: p.usage?.cost ?? null };
    }
    if (p.status === "failed") throw new Error(`${scene.id} failed: ${p.error || JSON.stringify(p).slice(0, 300)}`);
    if ((Date.now() - t0) / 1000 > 1500) throw new Error(`${scene.id} timed out, last status ${p.status}`);
  }
}

const results = await Promise.allSettled(todo.map((s, i) => sleep(i * 1500).then(() => run(s))));
const summary = results.map((r, i) => (r.status === "fulfilled" ? r.value : { id: todo[i].id, error: String(r.reason.message || r.reason) }));
fs.writeFileSync(path.join(OUT, "jobs.json"), JSON.stringify(summary, null, 2));
const total = summary.reduce((s, r) => s + (Number(r.cost) || 0), 0);
console.log("\nSUMMARY", JSON.stringify(summary, null, 2), `\nTotal cost: $${total.toFixed(2)}`);
