/**
 * Construye el sitio, levanta `astro preview` y lo apaga pase lo que pase.
 *
 * `astro preview` se demoniza solo: el proceso en primer plano sale de inmediato y el servidor
 * queda de fondo. Por eso no sirve el `webServer` de Playwright (lo da por caído) ni basta con
 * matar al proceso que lo lanzó — hay que pedirle `preview stop`.
 */
import { spawnSync } from "node:child_process";

const ASTRO = "node_modules/astro/bin/astro.mjs";

const astro = (...args) => spawnSync(process.execPath, [ASTRO, ...args], { stdio: "inherit" });

/** Corre `task()` con el sitio construido y servido; devuelve su código de salida. */
export async function withPreview(task) {
  astro("build");
  astro("preview", "--background");
  try {
    return await task("http://localhost:4321");
  } finally {
    astro("preview", "stop");
  }
}

export function run(command, ...args) {
  return spawnSync(process.execPath, [command, ...args], { stdio: "inherit" }).status ?? 1;
}
