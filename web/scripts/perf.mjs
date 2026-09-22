/**
 * Lighthouse en modo móvil, solo el LCP, contra el sitio construido (F7.7, extendido en F7.9
 * a `/arrival-guide` — su hero tiene el mismo poster pesado como LCP).
 *
 * El criterio de F7.7 es literal: "LCP < 2.5 s en Lighthouse móvil". No una categoría completa
 * (`performance`, que castigaría cosas de fases futuras, como los tamaños de imagen de F7.11 o
 * los presupuestos de red de F7.15) — solo la métrica que este paso promete.
 *
 * Usa el Chromium de Playwright, igual que `seo.mjs`, para correr igual aquí y en CI.
 *
 *   npm run perf                      # / y /arrival-guide (default de package.json)
 *   node scripts/perf.mjs /otra-ruta  # una ruta puntual
 */
import { chromium } from "@playwright/test";
import * as chromeLauncher from "chrome-launcher";
import lighthouse from "lighthouse";

import { withPreview } from "./preview.mjs";

const LCP_BUDGET_MS = 2500;

process.exitCode = await withPreview(async (origin) => {
  const paths = process.argv.slice(2);
  const urls = (paths.length === 0 ? ["/"] : paths).map((path) =>
    path.startsWith("http") ? path : `${origin}${path}`,
  );

  const chrome = await chromeLauncher.launch({
    chromePath: chromium.executablePath(),
    chromeFlags: ["--headless=new", "--no-sandbox", "--disable-gpu"],
  });

  let failed = false;
  try {
    for (const url of urls) {
      // Preset móvil por default (CPU 4x y viewport de teléfono). `throttlingMethod: "devtools"`
      // en vez del `"simulate"` de default: el video del hero se difiere con
      // `requestIdleCallback` (F7.7), y Lantern —el simulador de "simulate", que estima la red a
      // partir del grafo de dependencias de una carga sin acelerar— no entiende esa espera: ve
      // el video "temprano" en el trazo real y lo simula compitiendo por ancho de banda con el
      // poster, aunque en el navegador de verdad nunca pasa. `"devtools"` acelera la red de
      // verdad durante la carga, así que si respeta el diferido, se nota en la medición.
      // Cambió justo el día que se arregló ese diferido: de ~2.8 s (con la competencia) a ~1.9 s.
      const { lhr } = await lighthouse(url, {
        port: chrome.port,
        onlyCategories: ["performance"],
        throttlingMethod: "devtools",
        output: "json",
        logLevel: "error",
      });

      const lcp = lhr.audits["largest-contentful-paint"];
      const seconds = (lcp.numericValue / 1000).toFixed(2);
      console.log(`LCP ${seconds}s (móvil) — ${url}`);

      if (lcp.numericValue >= LCP_BUDGET_MS) {
        console.log(`  ✗ supera el presupuesto de ${LCP_BUDGET_MS / 1000}s`);
        failed = true;
      }
    }
  } finally {
    try {
      // Ver el comentario de `seo.mjs`: EPERM síncrono de chrome-launcher en Windows.
      chrome.kill();
    } catch {
      /* vacío a propósito */
    }
  }

  return failed ? 1 : 0;
});
