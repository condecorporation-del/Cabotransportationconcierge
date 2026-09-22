import { expect, test } from "@playwright/test";

/** F7.7. El hero: poster como LCP, video diferido, versión móvil y `prefers-reduced-motion`. */

test("el poster está listo para pintar sin depender de JS ni del video", async ({ page }) => {
  await page.goto("/");
  const poster = page.locator("[data-hero-poster]");

  await expect(poster).toHaveAttribute("fetchpriority", "high");
  await expect(poster).toHaveAttribute("loading", "eager");
  await expect(poster).toHaveAttribute("decoding", "async");
  // Varios anchos (no solo el original de 2000 px): un teléfono no debe bajar el mismo peso
  // que un monitor de escritorio.
  await expect(poster).toHaveAttribute("srcset", /\d+w.*\d+w/);
});

test("el poster se precarga con el mismo ancho que de verdad va a usar", async ({ page }) => {
  await page.goto("/");
  const preload = page.locator('link[rel="preload"][as="image"]');
  await expect(preload).toHaveCount(1);
  await expect(preload).toHaveAttribute("fetchpriority", "high");

  // Si el preload pidiera un ancho distinto al que el <img> real usa, el navegador bajaría el
  // archivo dos veces — exactamente lo que se corrigió al compartir `HERO_POSTER_WIDTHS`.
  const [preloadSrcset, imgSrcset] = await Promise.all([
    preload.getAttribute("imagesrcset"),
    page.locator("[data-hero-poster]").getAttribute("srcset"),
  ]);
  expect(preloadSrcset).toBe(imgSrcset);
});

test("sin JavaScript, el hero llega completo: título, texto y CTA", async ({ browser }) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  const page = await context.newPage();
  await page.goto("/");

  const hero = page.locator("section[aria-label='Hero']");
  await expect(hero.getByRole("heading", { level: 1 })).toBeVisible();
  // `exact`: la home también tiene un "Compare & reserve transfer" más abajo.
  await expect(hero.getByRole("link", { name: "Reserve transfer", exact: true })).toHaveAttribute(
    "href",
    "/book",
  );
  await expect(page.locator("[data-hero-poster]")).toBeVisible();

  await context.close();
});

test.describe("video del hero", () => {
  test("se difiere: no hay <source> hasta después de la carga inicial", async ({ page }) => {
    await page.goto("/", { waitUntil: "commit" });
    const hasSourceImmediately = await page.evaluate(
      () => document.querySelector("[data-hero-video] source") !== null,
    );
    expect(hasSourceImmediately).toBe(false);
  });

  test("termina reproduciéndose, con las fuentes ligeras", async ({ page }) => {
    await page.goto("/");
    await page.waitForFunction(
      () => {
        const video = document.querySelector<HTMLVideoElement>("[data-hero-video]");
        return !!video && !video.paused && video.readyState >= 2;
      },
      { timeout: 10_000 },
    );

    const sources = await page.$$eval("[data-hero-video] source", (nodes) =>
      nodes.map((node) => node.getAttribute("src")),
    );
    expect(sources).toEqual(["/videos/hero-promo-light.webm", "/videos/hero-promo-light.mp4"]);
  });

  test("con menos movimiento, el video nunca carga y el poster no anima", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.goto("/");
    await page.waitForTimeout(1500); // más que de sobra para el `requestIdleCallback` diferido

    const hasSource = await page.evaluate(
      () => document.querySelector("[data-hero-video] source") !== null,
    );
    expect(hasSource).toBe(false);

    const animationName = await page.evaluate(
      () => getComputedStyle(document.querySelector("[data-hero-poster]")!).animationName,
    );
    expect(animationName).toBe("none");

    await context.close();
  });
});

test("en móvil, el video sigue siendo 16:9 y el texto no se desborda", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");

  const frame = page.locator("[data-hero-frame]");
  const box = await frame.boundingBox();
  expect(box).not.toBeNull();
  // 16:9 ± un par de píxeles de redondeo.
  expect(box!.width / box!.height).toBeGreaterThan(1.7);
  expect(box!.width / box!.height).toBeLessThan(1.85);

  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBe(0);
});
