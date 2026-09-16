/**
 * Lighthouse, solo la categoría SEO, contra el sitio construido (F7.3).
 *
 * Usa el Chromium que ya bajó Playwright en vez de pedir un Chrome del sistema: así corre igual
 * en la máquina de desarrollo y en CI, sin instalar un navegador más.
 *
 *   npm run seo
 */
import { chromium } from "@playwright/test";
import * as chromeLauncher from "chrome-launcher";
import lighthouse from "lighthouse";

import { withPreview } from "./preview.mjs";

process.exitCode = await withPreview(async (origin) => {
  const urls = process.argv.slice(2);
  if (urls.length === 0) urls.push(`${origin}/`);

  const chrome = await chromeLauncher.launch({
    chromePath: chromium.executablePath(),
    chromeFlags: ["--headless=new", "--no-sandbox", "--disable-gpu"],
  });

  let failed = false;
  try {
    for (const url of urls) {
      const { lhr } = await lighthouse(url, {
        port: chrome.port,
        onlyCategories: ["seo"],
        output: "json",
        logLevel: "error",
      });

      const score = Math.round((lhr.categories.seo.score ?? 0) * 100);
      console.log(`SEO ${score}/100 — ${url}`);

      for (const ref of lhr.categories.seo.auditRefs) {
        const audit = lhr.audits[ref.id];
        // score null = auditoría informativa, no aplica al puntaje.
        if (audit.score !== null && audit.score < 1) {
          console.log(`  ✗ ${audit.title}`);
          failed = true;
        }
      }
      if (score < 100) failed = true;
    }
  } finally {
    try {
      // En Windows, chrome-launcher borra su perfil temporal antes de que Chrome suelte los
      // archivos y revienta con EPERM (de forma síncrona, así que no basta un `.catch`). Es
      // basura en %TEMP%, no un fallo de la revisión.
      chrome.kill();
    } catch {
      /* vacío a propósito */
    }
  }

  return failed ? 1 : 0;
});
