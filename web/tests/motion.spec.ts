import { expect, test } from "@playwright/test";

/** F7.8. Reveal al hacer scroll, brillo dorado y barra de progreso — la única isla con JS de
 *  esta tarea es `Motion.astro`, y su criterio es literal: menos de 5 KB. */

test("el script de Motion pesa menos de 5 KB", async ({ request }) => {
  const html = await (await request.get("/")).text();
  // Se identifica por su contenido (marca `data-progress`), no por posición: en la página hay
  // otros `<script type="module">` (el header, el video del hero).
  const match = html.match(/<script type="module">([^<]*data-progress[^<]*)<\/script>/);
  expect(match, "no se encontró el script de Motion en el HTML").not.toBeNull();

  const bytes = Buffer.byteLength(match![1]!, "utf-8");
  expect(bytes, `Motion pesa ${bytes} bytes`).toBeLessThan(5 * 1024);
});

test("el contenido marcado para revelar empieza oculto y aparece al entrar en pantalla", async ({
  page,
}) => {
  await page.goto("/");
  const target = page.locator("[data-reveal]").first();

  // Fuera de pantalla todavía (arriba del todo, recién cargó): no tiene `.is-in`.
  await expect(target).not.toHaveClass(/is-in/);

  await target.scrollIntoViewIfNeeded();
  await expect(target).toHaveClass(/is-in/);
  await expect(target).toHaveCSS("opacity", "1");
});

test("con menos movimiento, todo el reveal aparece de una vez, sin esperar scroll", async ({
  browser,
}) => {
  const context = await browser.newContext({ reducedMotion: "reduce" });
  const page = await context.newPage();
  await page.goto("/");
  await page.waitForTimeout(300);

  // El último [data-reveal] de la página (muy abajo, nunca llegó a la pantalla) ya está
  // marcado: con menos movimiento, Motion los marca todos de inmediato, no uno por uno.
  const last = page.locator("[data-reveal]").last();
  await expect(last).toHaveClass(/is-in/);

  await context.close();
});

test("sin JavaScript, el contenido marcado para revelar ya es visible", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/");

  const count = await page.locator("[data-reveal]").count();
  expect(count).toBeGreaterThan(0);
  await expect(page.locator("[data-reveal]").last()).toHaveCSS("opacity", "1");

  await context.close();
});

test("la barra de progreso avanza con el scroll", async ({ page }) => {
  await page.goto("/");
  const bar = page.locator("[data-progress]");

  const atTop = await bar.evaluate((el) => getComputedStyle(el).transform);
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight / 2));
  await page.waitForTimeout(100);
  const halfway = await bar.evaluate((el) => getComputedStyle(el).transform);

  expect(halfway).not.toBe(atTop);
});

test("el brillo dorado no compite con el video del hero por el mismo botón", async ({ page }) => {
  // Solo verifica que el CTA sólido del hero (el único "brillo dorado" arriba del pliegue)
  // trae la clase y sigue siendo el mismo enlace de siempre — F7.7 no debe romperse por F7.8.
  await page.goto("/");
  const cta = page.locator("section[aria-label='Hero'] a.ctc-shine");
  await expect(cta).toHaveAttribute("href", "/book");
});
