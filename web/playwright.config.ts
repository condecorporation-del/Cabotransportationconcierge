import { defineConfig, devices } from "@playwright/test";

/** F7.1. Corre contra el build real (`astro preview`), no contra el dev server: lo que se
 *  verifica es el HTML que de verdad se publica. Quien levanta y apaga el servidor es
 *  `scripts/e2e.mjs`, no el `webServer` de Playwright: ver el comentario de ese archivo. */
export default defineConfig({
  testDir: "./tests",
  use: { baseURL: "http://localhost:4321" },
  projects: [{ name: "chromium", use: devices["Desktop Chrome"] }],
});
