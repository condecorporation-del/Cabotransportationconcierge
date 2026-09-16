import { expect, test } from "@playwright/test";

const DESKTOP = { width: 1440, height: 900 };
const PHONE = { width: 390, height: 800 };

test.describe("mega menú en escritorio", () => {
  test.use({ viewport: DESKTOP });

  test("abre al pasar el mouse por Services", async ({ page }) => {
    await page.goto("/");
    const panel = page.locator("[data-mega]");
    await expect(panel).toBeHidden();

    await page.getByRole("button", { name: "Services" }).hover();
    await expect(panel).toBeVisible();
    await expect(page.getByRole("link", { name: "Bisbee's Black & Blue" })).toBeVisible();
  });

  test("abre con el teclado y cierra con Escape", async ({ page }) => {
    await page.goto("/");
    const services = page.getByRole("button", { name: "Services" });
    const panel = page.locator("[data-mega]");

    await services.focus();
    await expect(panel).toBeVisible(); // :focus-within, sin depender del script

    await services.press("Enter");
    await expect(services).toHaveAttribute("aria-expanded", "true");

    await page.keyboard.press("Escape");
    await expect(services).toHaveAttribute("aria-expanded", "false");
  });

  test("al bajar, el header se compacta y el CTA sigue visible", async ({ page }) => {
    await page.goto("/");
    const header = page.locator("[data-header]");
    await expect(header).not.toHaveAttribute("data-scrolled", /.*/);

    await page.evaluate(() => window.scrollTo(0, 600));
    await expect(header).toHaveAttribute("data-scrolled", "");
    await expect(page.getByRole("link", { name: "Reserve", exact: true })).toBeVisible();
  });
});

test.describe("menú móvil", () => {
  test.use({ viewport: PHONE });

  test("abre a pantalla completa y cierra con Escape", async ({ page }) => {
    await page.goto("/");
    const panel = page.locator("[data-mobile-panel]");
    await expect(panel).toBeHidden();

    await page.locator("[data-mobile] > summary").click();
    await expect(panel).toBeVisible();

    // Pantalla completa de verdad: el <details> vive dentro del header, y si algún ancestro
    // vuelve a tener `backdrop-filter` o `transform`, el panel `fixed` se queda encerrado ahí.
    const box = await panel.boundingBox();
    expect(box?.width).toBe(PHONE.width);
    expect(box?.height).toBe(PHONE.height);
    expect(box?.y).toBe(0);

    await page.keyboard.press("Escape");
    await expect(panel).toBeHidden();
  });

  test("con el menú abierto, los flotantes no tapan el CTA de reservar", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-mobile] > summary").click();

    await expect(page.locator("[data-floating-actions]")).toBeHidden();
    await expect(
      page.locator("[data-mobile-panel]").getByRole("link", { name: "Reserve" }),
    ).toBeVisible();
  });

  test("el fondo no se desplaza mientras el menú está abierto", async ({ page }) => {
    await page.goto("/");
    await page.locator("[data-mobile] > summary").click();
    await expect(page.locator("body")).toHaveCSS("overflow", "hidden");
  });
});

test("todos los destinos del menú existen en el HTML sin JavaScript", async ({
  browser,
  request,
}) => {
  // Criterio de F7.4. Si el mega menú se armara con JS, un rastreador —y cualquiera con el JS
  // caído— vería un sitio sin enlaces internos.
  //
  // Se mira el HTML crudo, no el árbol de accesibilidad: con el menú cerrado los enlaces están
  // en `visibility: hidden`, que es justo lo correcto para un menú cerrado (un lector de
  // pantalla no debe leerlos), pero un rastreador sí los ve porque están en el documento.
  const html = await (await request.get("/")).text();
  for (const href of [
    "/cabo-transportation",
    "/los-cabos-hotel-shuttles",
    "/private-bilingual-driver",
    "/weddings",
    "/limousines",
    "/city-tours",
    "/cabo-airport-flights",
  ]) {
    expect(html, `falta el enlace ${href}`).toContain(`href="${href}"`);
  }

  // Y sin script el menú sigue abriéndose con el mouse, porque la apertura es CSS.
  const context = await browser.newContext({ javaScriptEnabled: false, viewport: DESKTOP });
  const page = await context.newPage();
  await page.goto("/");

  await page.getByRole("button", { name: "Services" }).hover();
  await expect(page.locator("[data-mega]")).toBeVisible();
  await expect(page.getByRole("link", { name: "All Cabo Transfers" })).toBeVisible();

  await context.close();
});
