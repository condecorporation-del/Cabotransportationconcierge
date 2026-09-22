import { expect, test } from "@playwright/test";

/** F7.6. La home se arma con el contenido extraído del prototipo aprobado. Estas pruebas
 *  vigilan que el porte no pierda secciones ni deje entrar basura del extractor. */

test("están las 26 secciones que se publican del prototipo", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("main section")).toHaveCount(26);
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

test.describe("tarjetas de zona", () => {
  test("son cinco, con los nombres propios de CTC y no los de la referencia", async ({ page }) => {
    await page.goto("/");
    const cards = page.locator("section:nth-of-type(4) li");
    await expect(cards).toHaveCount(5);

    // §3.5.6: mismos límites geográficos, nombres propios. Si alguna vez vuelven los de la
    // referencia ("Tourist Corridor", "Cabo Pacific Area"), esto falla.
    await expect(cards.nth(0)).toContainText("San José del Cabo & Estuary");
    await expect(cards.nth(1)).toContainText("The Corridor & Puerto Los Cabos");
    await expect(cards.nth(2)).toContainText("Cabo San Lucas & Marina");
  });

  test("cada tarjeta trae su tarifa y su tiempo de viaje reales", async ({ page }) => {
    await page.goto("/");
    const cards = page.locator("section:nth-of-type(4) li");

    for (let i = 0; i < 5; i += 1) {
      const card = cards.nth(i);
      // Un precio de verdad, no un guion: si el catálogo se queda sin tarifas, se nota aquí.
      await expect(card).toContainText(/\$\d{2,3}/);
      await expect(card).toContainText(/\d+–\d+ min from SJD/);
      await expect(card.getByRole("link", { name: "See rates" })).toBeVisible();
    }
  });
});

test("las fichas de flota traen la flota real de CTC", async ({ page }) => {
  await page.goto("/");
  const cards = page.locator("section:nth-of-type(6) li");
  await expect(cards).toHaveCount(5);

  // Capacidades del catálogo: la Suburban lleva 5 y el Sprinter 17. Si alguien copia estos
  // números del prototipo de la referencia en vez de leerlos del catálogo, aquí se nota.
  await expect(cards.nth(0)).toContainText("Chevrolet Suburban");
  await expect(cards.nth(0)).toContainText("5 guests");
  await expect(cards.nth(4)).toContainText("Mercedes-Benz Sprinter");
  await expect(cards.nth(4)).toContainText("17 guests");
  await expect(cards.nth(4)).toContainText("17 bags");
});

test("no se publica prueba social de la referencia", async ({ page }) => {
  // D-P3: el prototipo es un espejo rebrandeado y arrastra las cifras de la referencia —"5.0
  // Google reviews (901)", "since 2013", "#1 in Cabo"—. CTC es nueva y no tiene ninguna.
  // Publicarlas sería decirle al viajero algo falso donde decide si confiar su llegada.
  await page.goto("/");
  const body = (await page.locator("body").textContent()) ?? "";

  for (const claim of [/Google\s*reviews/i, /since\s+20\d\d/i, /#1\s+in\s+Cabo/i, /TripAdvisor/i]) {
    expect(body, `se coló una afirmación de la referencia: ${claim}`).not.toMatch(claim);
  }
});

test("la sección de testimonios no está", async ({ page }) => {
  // Vuelve en F16.1, con las reseñas reales de CTC y su enlace de origen.
  await page.goto("/");
  await expect(page.locator("#testimonials")).toHaveCount(0);
});

test.describe("rejilla de servicios", () => {
  test("son seis fichas, a sangre y con foto, título y CTA", async ({ page }) => {
    await page.goto("/");
    const grid = page.locator("#services-grid");
    const tiles = grid.locator("li");
    await expect(tiles).toHaveCount(6);

    for (const [title, cta] of [
      ["Weddings", "Discover"],
      ["Bachelorette", "Plan the trip"],
      ["Groups", "Plan now"],
      ["Family", "See options"],
      ["Limousines", "Reserve"],
      ["City tours", "Explore"],
    ] as const) {
      const tile = tiles.filter({ hasText: title });
      await expect(tile).toHaveCount(1);
      await expect(tile).toContainText(cta);
      await expect(tile.locator("img")).toHaveAttribute("alt", /.+/);
    }
  });

  test("cada ficha enlaza a la página real del servicio, no a un ancla vacía", async ({ page }) => {
    // El prototipo deja las seis en href="#"; esas páginas de servicio son F9, pero ya existen
    // como destino en el mega menú (§3.5.2) y no hay razón para no usarlas ya.
    await page.goto("/");
    const tiles = page.locator("#services-grid li a");
    const hrefs = await tiles.evaluateAll((links) => links.map((a) => a.getAttribute("href")));

    expect(hrefs).toEqual([
      "/weddings",
      "/bachelorette-party-transportation",
      "/group-transfers",
      "/family-transportation",
      "/limousines",
      "/city-tours",
    ]);
  });

  test("la rejilla llega a los bordes del viewport, sin el gutter del resto de secciones", async ({
    page,
  }) => {
    await page.goto("/");
    const box = await page.locator("#services-grid li").first().boundingBox();
    expect(box?.x).toBe(0);
  });
});

test("el FAQ no arrastra botones ni fotos del footer", async ({ page }) => {
  // Bug real de extracción: la sección del FAQ es la última del prototipo y, sin acotar cada
  // sección a su propio </section>, se quedaba con todo lo que viene después — el <footer>
  // completo. Se coló como si fueran suyos un botón y una foto que en realidad son del pie de
  // página. Ver `scripts/lib/prototype-html.mjs`.
  await page.goto("/");
  const faqSection = page.locator("#faq");
  const ctas = faqSection.getByRole("link", { name: /get a quote/i });
  await expect(ctas).toHaveCount(1);
  await expect(faqSection.locator("img")).toHaveCount(0);
});
