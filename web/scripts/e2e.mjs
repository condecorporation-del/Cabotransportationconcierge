/**
 * Corre Playwright contra el build real.
 *
 * El `webServer` de Playwright no sirve aquí: `astro preview` se demoniza solo, así que el
 * proceso en primer plano sale de inmediato y Playwright lo toma por un servidor caído. Este
 * script maneja el ciclo de vida del demonio a mano y lo apaga pase lo que pase.
 */
import { spawnSync } from "node:child_process";

const astro = ["node_modules/astro/bin/astro.mjs"];
const run = (args) => spawnSync(process.execPath, [...astro, ...args], { stdio: "inherit" });

run(["build"]);
run(["preview", "--background"]);
try {
  const tests = spawnSync(
    process.execPath,
    ["node_modules/@playwright/test/cli.js", "test", ...process.argv.slice(2)],
    { stdio: "inherit" },
  );
  process.exitCode = tests.status ?? 1;
} finally {
  run(["preview", "stop"]);
}
