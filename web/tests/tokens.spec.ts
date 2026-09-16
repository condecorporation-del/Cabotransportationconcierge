import { expect, test } from "@playwright/test";

/** F7.2. Que el CSS diga `font-family: Cinzel` no prueba nada: si el WOFF2 no carga, el
 *  navegador cae en silencio a Georgia y la página se ve casi igual en una captura. Por eso
 *  estas pruebas miran la familia calculada y además le preguntan al navegador si la fuente
 *  de verdad está disponible. */

const FACES = [
  { token: "brand", family: "Cinzel", probe: '600 16px "Cinzel"' },
  { token: "display", family: "Cormorant Garamond", probe: '600 16px "Cormorant Garamond"' },
  { token: "body", family: "Manrope", probe: '400 16px "Manrope"' },
];

for (const { token, family, probe } of FACES) {
  test(`${family} se aplica y carga de verdad`, async ({ page }) => {
    await page.goto("/");
    await page.evaluate(() => document.fonts.ready);

    const element = page.locator(`[data-token="${token}"]`);
    await expect(element).toHaveCSS("font-family", new RegExp(`^["']?${family}`));

    const loaded = await page.evaluate(async (descriptor) => {
      await document.fonts.load(descriptor);
      return document.fonts.check(descriptor);
    }, probe);
    expect(loaded, `${family} no cargó: el navegador está usando la fuente de respaldo`).toBe(true);
  });
}

test("las fuentes se sirven desde el propio sitio, no desde Google", async ({ page }) => {
  const hosts = new Set<string>();
  page.on("request", (request) => {
    if (request.resourceType() === "font") hosts.add(new URL(request.url()).host);
  });

  await page.goto("/");
  await page.evaluate(() => document.fonts.ready);

  expect([...hosts]).toEqual(["localhost:4321"]);
});

test("la paleta de marca llega a la página", async ({ page }) => {
  await page.goto("/");
  // El cuerpo del sitio es claro (así es el prototipo aprobado); el obsidiana queda para el
  // header, el footer, el hero y los paneles destacados.
  await expect(page.locator("body")).toHaveCSS("background-color", "rgb(249, 250, 251)");
  await expect(page.locator('[data-token="brand"]')).toHaveCSS("color", "rgb(158, 124, 62)");
  await expect(page.locator("footer")).toHaveCSS("background-color", "rgb(12, 15, 20)");
});

test("a 360 px la página no se desborda de lado", async ({ page }) => {
  // El ancho más angosto de la matriz de D16. Un solo elemento que se pase rompe el scroll
  // horizontal de toda la página, y es el error más fácil de meter sin notarlo.
  await page.setViewportSize({ width: 360, height: 780 });
  await page.goto("/");
  await page.evaluate(() => document.fonts.ready);

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBe(0);
});
