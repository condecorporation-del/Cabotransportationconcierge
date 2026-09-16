import { expect, test } from "@playwright/test";

const SITE = "https://www.cabotransportationconcierge.com";

test.describe("cabeza de la página", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/");
  });

  test("el canonical y los hreflang son absolutos y apuntan al dominio real", async ({ page }) => {
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute("href", `${SITE}/`);
    await expect(page.locator('link[hreflang="en"]')).toHaveAttribute("href", `${SITE}/`);
    await expect(page.locator('link[hreflang="es"]')).toHaveAttribute("href", `${SITE}/es/`);
    await expect(page.locator('link[hreflang="x-default"]')).toHaveAttribute("href", `${SITE}/`);
  });

  test("las etiquetas para compartir están completas", async ({ page }) => {
    await expect(page.locator('meta[property="og:title"]')).toHaveAttribute("content", /Cabo/);
    await expect(page.locator('meta[property="og:url"]')).toHaveAttribute("content", `${SITE}/`);
    await expect(page.locator('meta[property="og:locale"]')).toHaveAttribute("content", "en_US");
    const description = await page.locator('meta[name="description"]').getAttribute("content");
    // Rango de §12: ni un resumen de dos palabras ni un párrafo que Google corte.
    expect(description?.length).toBeGreaterThan(80);
    expect(description?.length).toBeLessThan(170);
  });

  test("el JSON-LD es válido y describe a la empresa", async ({ page }) => {
    const raw = await page.locator('script[type="application/ld+json"]').textContent();
    const data = JSON.parse(raw ?? "");
    expect(data["@type"]).toBe("Organization");
    expect(data.url).toBe(SITE);
  });
});

test("el enlace de salto aparece al tabular y lleva al contenido", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("Tab");

  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await expect(skip).toBeVisible();

  await page.keyboard.press("Enter");
  expect(await page.evaluate(() => window.location.hash)).toBe("#main");
});

test("mientras el contacto sea provisional no se publica ningún número", async ({ page }) => {
  await page.goto("/");

  // D-P4: los datos reales salen de company_settings y todavía no existen. Publicar el
  // placeholder como si fuera un teléfono real mandaría a la gente a un número inventado.
  // Aparece dos veces a propósito: en la barra superior del header y en el footer.
  await expect(page.locator("[data-contact='pending']").first()).toBeVisible();
  await expect(page.locator('a[href^="tel:"]')).toHaveCount(0);
  await expect(page.locator('a[href*="wa.me"]')).toHaveCount(0);

  const help = page.locator("[data-customer-help]");
  await expect(help).toBeVisible();
  await expect(help).toBeDisabled();
});
