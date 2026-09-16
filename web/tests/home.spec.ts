import { expect, test } from "@playwright/test";

/** F7.6. La home se arma con el contenido extraído del prototipo aprobado. Estas pruebas
 *  vigilan que el porte no pierda secciones ni deje entrar basura del extractor. */

test("están las 27 secciones del prototipo", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("main section")).toHaveCount(27);
});

test("cada sección con título lleva su barra dorada", async ({ page }) => {
  await page.goto("/");
  const headings = await page.locator("main section h2").count();
  expect(headings).toBeGreaterThan(20);
  await expect(page.locator("main section header span")).toHaveCount(headings);
});

test("el FAQ abre y cierra sin JavaScript", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/");

  const first = page.locator("#faq details").first();
  const answer = first.locator("p");
  await expect(answer).toBeHidden();

  await first.locator("summary").click();
  await expect(answer).toBeVisible();

  await context.close();
});

test("no se cuela el formulario de reserva como si fuera texto", async ({ page }) => {
  // El cotizador vive dentro de un <p> sin cerrar en el prototipo; si el filtro del extractor
  // se rompe, sus rótulos aparecen como un párrafo suelto en la página.
  await page.goto("/");
  const body = (await page.locator("main").textContent()) ?? "";
  expect(body).not.toContain("Estimated Total");
  expect(body).not.toContain("Select a vehicle to continue");
});

test("todas las fotos tienen alt y medidas", async ({ page }) => {
  await page.goto("/");
  const images = page.locator("main img");
  const total = await images.count();
  expect(total).toBeGreaterThan(20);

  let described = 0;
  for (let i = 0; i < total; i += 1) {
    const image = images.nth(i);
    // El atributo tiene que existir siempre; vacío es la forma correcta de marcar una imagen
    // decorativa, y el prototipo dejó una así. Las fotos definitivas y sus textos son F7.11.
    expect(await image.getAttribute("alt")).not.toBeNull();
    await expect(image).toHaveAttribute("width", /\d+/);
    await expect(image).toHaveAttribute("height", /\d+/);
    if (((await image.getAttribute("alt")) ?? "").length > 0) described += 1;
  }
  expect(described).toBeGreaterThanOrEqual(total - 1);
});
