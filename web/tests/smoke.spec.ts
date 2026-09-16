import { expect, test } from "@playwright/test";

test("la página llega como HTML real, sin depender de JavaScript", async ({ request }) => {
  // El punto entero de haber elegido Astro (D3): un rastreador que no ejecuta JS ve la página
  // completa, no un cascarón vacío.
  const html = await (await request.get("/")).text();
  expect(html).toContain("Cabo Transportation Concierge");
  expect(html).toContain("Cabo airport transportation from Los Cabos International Airport");
});

test("sin JavaScript la home sigue completa y navegable", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/");

  await expect(page.locator("main section")).toHaveCount(26);
  await expect(page.getByRole("link", { name: "Reserve", exact: true }).first()).toBeVisible();

  await context.close();
});
