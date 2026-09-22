/**
 * Copia el video y el poster del hero, ya aprobados, a sus destinos en `web/` (F7.7).
 *
 * El poster va a `src/assets/`, no a `public/`: tiene que pasar por `astro:assets` para salir en
 * varios anchos (móvil no necesita los 2000 px de ancho del original — mandarlos completos es
 * lo que hacía fallar el presupuesto de LCP de §12.1, ver bitácora).
 *
 * Del video solo la pareja **ligera** (`hero-promo-light.{mp4,webm}`, ~6 MB cada uno): la
 * versión pesada (`hero-promo.{mp4,webm}`, 12-14 MB) no cabe ni en su propio presupuesto de
 * escritorio de §12.1 (≤ 6.5 MB) — hay que recodificarla, no solo copiarla, y eso es trabajo de
 * F7.15 (presupuestos de carga y video según la conexión). Cargar la pesada ahora para tirarla
 * en F7.15 no ahorra nada; mejor un solo video "ligero" para todas las pantallas mientras tanto.
 *
 * Los tres archivos ya están versionados en `site/` (a diferencia de la pareja de video pesada
 * y de `video.mp4`, que `.gitignore` excluye por regenerables); por eso alcanza con copiarlos,
 * sin `ffmpeg` ni `site/video/compose.mjs`.
 *
 *   npm run extract:hero-media
 */
import { copyFile, mkdir } from "node:fs/promises";
import path from "node:path";

const SITE_DIR = path.join("..", "site");
const VIDEO_FILES = ["hero-promo-light.mp4", "hero-promo-light.webm"];
const VIDEO_OUT = path.join("public", "videos");
const POSTER_OUT = path.join("src", "assets", "hero-suburban.jpg");

await mkdir(VIDEO_OUT, { recursive: true });
for (const name of VIDEO_FILES) {
  await copyFile(path.join(SITE_DIR, "videos", name), path.join(VIDEO_OUT, name));
}
await copyFile(path.join(SITE_DIR, "hero-suburban.jpg"), POSTER_OUT);

console.log(`${VIDEO_FILES.length} archivos de video -> ${VIDEO_OUT}`);
console.log(`poster -> ${POSTER_OUT}`);
