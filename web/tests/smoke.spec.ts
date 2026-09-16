import { expect, test } from "@playwright/test";

test("la página llega como HTML real, sin depender de JavaScript", async ({ request }) => {
  const html = await (await request.get("/")).text();
  expect(html).toContain("Cabo Transportation Concierge");
});

test("la isla de React se hidrata y responde al clic", async ({ page }) => {
  await page.goto("/");
  const island = page.getByRole("button", { name: "Probar la isla de React" });
  await expect(island).toBeVisible();
  await island.click();
  await expect(page.getByRole("button", { name: "React hidratado" })).toBeVisible();
});
