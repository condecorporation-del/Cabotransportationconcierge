import { expect, test } from "@playwright/test";

/** F7.9. `/arrival-guide`: estructura portada del prototipo, D-P6 (sin video, solo poster) y las
 *  mismas garantías de accesibilidad progresiva que ya tiene la home (F7.7/F7.8). */

test("trae las cinco secciones con su contenido", async ({ page }) => {
  await page.goto("/arrival-guide");

  await expect(page.getByRole("heading", { level: 1 })).toContainText("Cabo San Lucas");
  await expect(page.getByText("SJD Airport Guide")).toBeVisible();

  await expect(page.getByRole("heading", { name: "How to find us at SJD Airport" })).toBeVisible();

  await expect(page.getByRole("heading", { name: "Be Aware" })).toBeVisible();

  await expect(page.getByRole("heading", { name: "What to do once my plane lands" })).toBeVisible();
  await expect(page.locator("ol li")).toHaveCount(4);
  await expect(page.getByRole("heading", { name: "Look for the checkpoint" })).toBeVisible();

  await expect(page.getByRole("heading", { name: "Ready to Book your transfer?" })).toBeVisible();
});

test("D-P6: ningún <video> — el de la referencia muestra a su propia anfitriona", async ({
  page,
}) => {
  await page.goto("/arrival-guide");
  await expect(page.locator("video")).toHaveCount(0);
});

test("el CTA final reserva en una sola línea, sin envolver el texto", async ({ page }) => {
  await page.goto("/arrival-guide");
  const cta = page.locator("a.ctc-shine");

  await expect(cta).toHaveAttribute("href", "/book");
  const box = await cta.boundingBox();
  expect(box).not.toBeNull();
  // Una sola línea de "Reserve now" en mayúsculas con este tamaño no pasa de ~30px de alto
  // (párrafo padding incluido); si el texto se envuelve, la caja salta a más del doble.
  expect(box!.height).toBeLessThan(56);
});

test("sin JavaScript, el contenido ya es visible", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/arrival-guide");

  const count = await page.locator("[data-reveal]").count();
  expect(count).toBeGreaterThan(0);
  await expect(page.locator("[data-reveal]").last()).toHaveCSS("opacity", "1");
  await expect(page.getByRole("heading", { name: "Ready to Book your transfer?" })).toBeVisible();

  await context.close();
});

test("el poster del hero está listo para pintar sin depender de JS", async ({ page }) => {
  await page.goto("/arrival-guide");
  const poster = page.locator("section").first().locator("img").first();

  await expect(poster).toHaveAttribute("fetchpriority", "high");
  await expect(poster).toHaveAttribute("loading", "eager");
  await expect(poster).toHaveAttribute("srcset", /\d+w.*\d+w/);

  const preload = page.locator('link[rel="preload"][as="image"]');
  await expect(preload).toHaveCount(1);
  const [preloadSrcset, imgSrcset] = await Promise.all([
    preload.getAttribute("imagesrcset"),
    poster.getAttribute("srcset"),
  ]);
  expect(preloadSrcset).toBe(imgSrcset);
});

test("en móvil no hay desbordamiento horizontal", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/arrival-guide");

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBe(0);
});
