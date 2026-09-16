/** Playwright contra el build real, no contra el dev server: lo que se verifica es el HTML
 *  que de verdad se publica. El servidor lo maneja `preview.mjs`. */
import { run, withPreview } from "./preview.mjs";

process.exitCode = await withPreview(() =>
  run("node_modules/@playwright/test/cli.js", "test", ...process.argv.slice(2)),
);
