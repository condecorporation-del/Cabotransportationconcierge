/**
 * Saca el contenido de la home del prototipo aprobado a `src/content/home.json` (F7.6).
 *
 * El prototipo (`site/index.html`) es HTML generado, con las clases de Tailwind del build
 * original. Portarlo a mano, sección por sección, sería transcribir dos mil líneas y colar
 * erratas. En vez de eso el texto se extrae una vez y los componentes de Astro lo consumen:
 * así el porte cambia la *presentación* sin tocar el contenido.
 *
 * Los textos se reescriben en la voz de CTC en F9.1; aquí llegan tal cual están en el prototipo.
 *
 *   npm run extract:home
 */
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { all, rich, splitSections, stripBlock, text } from "./lib/prototype-html.mjs";

const SOURCE = path.join("..", "site", "index.html");
const OUT = path.join("src", "content", "home.json");
const IMAGE_DIR = path.join("public", "images", "home");

/**
 * El cotizador del primer bloque es un widget, no prosa — y en el prototipo vive dentro de un
 * `<p>` que nunca se cierra, así que el extractor de párrafos se traga sus etiquetas ("Drop-off
 * Location Where are we going?Arrival Date…"). Se descarta por sus rótulos: el cotizador de
 * verdad se conecta en F8 y no sale de aquí.
 */
const WIDGET_LABELS = [
  "Drop-off Location",
  "Arrival Date",
  "Estimated Total",
  "Select a vehicle",
  "Book My Ride",
  "Where are we picking you up",
];

function isWidgetChrome(value) {
  return WIDGET_LABELS.filter((label) => value.includes(label)).length >= 2;
}

/**
 * El prototipo es un espejo rebrandeado de la referencia, así que arrastra **su** prueba social:
 * "5.0 Google reviews (901)", "6,700 reseñas", "since 2013", "#1 in Cabo". CTC es nueva y no
 * tiene ninguna de esas cifras.
 *
 * La decisión ya estaba tomada en el plan (D-P3, §"Estrellas y reseñas"): datos reales del
 * cliente o se quita. Publicar calificaciones y antigüedad ajenas no es un detalle de porte —
 * es decirle al viajero algo falso justo donde está decidiendo si confiar su llegada. Las
 * reseñas de verdad se recogen en F16.1.
 */
const REFERENCE_CLAIMS = [
  /\b\d(?:\.\d)?\s*(?:★|stars?\b|-?star\b|rated\b)/i,
  // Sin `\b` delante: en el prototipo viene pegado al número ("5.0Google reviews(901)"), y
  // entre un dígito y una letra no hay límite de palabra.
  /Google\s*reviews?/i,
  /\d\.\d\s*(?:Google|star)/i,
  /\b\d{1,3},\d{3}\+?\s*(?:reviews?|guests?|trips?)\b/i,
  /\bsince\s+20\d\d\b/i,
  /#1\s+in\s+Cabo/i,
  /\b(?:TripAdvisor|Yelp)\b/i,
];

const dropped = [];

function isReferenceClaim(value) {
  const hit = REFERENCE_CLAIMS.some((pattern) => pattern.test(value));
  if (hit) dropped.push(value.replace(/<[^>]+>/g, "").slice(0, 110));
  return hit;
}

const html = await readFile(SOURCE, "utf8");
// La tarjeta promocional del velero (`phoenix-promo`, $100/persona, "RESERVE YOUR SAIL") vive
// *adentro* de la sección de info de SJD, no en su propia `<section>` — a diferencia del promo
// de $600 de más abajo, que sí abre su propia sección y por eso ya sale aparte. Sin quitarla de
// aquí, sus párrafos y su lista de features se cuelan como si fueran prosa del aeropuerto: no es
// contenido falso (D-P3 es sobre eso), es contenido de un servicio distinto mezclado a media
// oración con el de traslados. Se retira entera; su propia tarjeta queda pendiente.
const body = stripBlock(html.slice(html.indexOf("<body")), "phoenix-promo");

const sections = [];
for (const { openTag: open, inner: chunk } of splitSections(body)) {
  const heading = chunk.match(/<h[12][^>]*>(.*?)<\/h[12]>/s)?.[1];

  // La sección de testimonios es prueba social de la referencia de punta a punta: no se filtra
  // frase por frase, se quita entera (D-P3). Vuelve en F16.1 con las reseñas reales de CTC.
  if (/id="testimonials"/.test(open)) {
    dropped.push("(la sección de testimonios completa)");
    continue;
  }

  // `<p\b` y `<li\b`, no `<p[^>]*>` a secas: sin el límite de palabra, "<p" hace match con el
  // arranque de cualquier otra etiqueta que empiece con esa letra — un `<path>` de un ícono
  // SVG, por ejemplo — y el `.*?` no greedy sigue de largo hasta el primer `</p>` real,
  // tragándose de paso el título y lo que venga en medio. Costó una comparación bytes-a-bytes
  // encontrarlo: el párrafo de "Be Aware" en `/arrival-guide` salía con "Be Aware" duplicado
  // al principio, viniendo de un ícono de alerta con `<path>` antes del texto real.
  const paragraphs = all(/<p\b[^>]*>(.*?)<\/p>/gs, chunk)
    .map((m) => rich(m[1]))
    .filter(
      (p) => p.replace(/<[^>]+>/g, "").length > 40 && !isWidgetChrome(p) && !isReferenceClaim(p),
    );

  const bullets = all(/<li\b[^>]*>(.*?)<\/li>/gs, chunk)
    .map((m) => text(m[1]))
    .filter((b) => b.length > 3 && b.length < 220 && !isWidgetChrome(b) && !isReferenceClaim(b));

  // Botones: los <a> con fondo o borde, que en el prototipo son los CTA.
  const ctas = all(/<a\b([^>]*)>(.*?)<\/a>/gs, chunk)
    .filter(([, attrs]) => /class="[^"]*(bg-\[|border-2|inline-flex)/.test(attrs))
    .map(([, attrs, inner]) => ({
      label: text(inner),
      href: attrs.match(/href="([^"]*)"/)?.[1] ?? "#",
    }))
    .filter((cta) => cta.label && cta.label.length < 40);

  const images = all(/<img\b([^>]*)>/g, chunk)
    .map(([, attrs]) => ({
      src: attrs.match(/src="([^"]*)"/)?.[1] ?? "",
      alt: text(attrs.match(/alt="([^"]*)"/)?.[1] ?? ""),
    }))
    .filter((image) => image.src && !image.src.startsWith("data:"));

  // El FAQ del prototipo ya son <details>/<summary>, el mismo patrón que usa el menú móvil.
  const faq = all(/<details\b[^>]*>(.*?)<\/details>/gs, chunk)
    .map(([, inner]) => ({
      question: text(inner.match(/<summary[^>]*>(.*?)<\/summary>/s)?.[1] ?? ""),
      answer: rich(inner.replace(/<summary[^>]*>.*?<\/summary>/s, "")),
    }))
    .filter((entry) => entry.question && entry.answer && !isReferenceClaim(entry.answer));

  // La rejilla de servicios: seis fichas foto+título+CTA, cada una un <a> que envuelve la
  // imagen y dos <span> (título grande, "tile-cta"). Su estructura no encaja en párrafos, listas
  // ni CTA de botón, así que se extrae aparte, solo dentro de esta sección.
  const tiles =
    open.includes('id="services-grid"') === false
      ? []
      : all(/<a\b[^>]*>(.*?)<\/a>/gs, chunk).map(([, inner]) => ({
          title: text(inner.match(/text-3xl[^>]*>(.*?)<\/span>/s)?.[1] ?? ""),
          cta: text(inner.match(/tile-cta[^>]*>(.*?)<\/span>/s)?.[1] ?? ""),
          image: {
            src: inner.match(/src="([^"]*)"/)?.[1] ?? "",
            alt: text(inner.match(/alt="([^"]*)"/)?.[1] ?? ""),
          },
        }));

  sections.push({
    id: open.match(/id="([^"]+)"/)?.[1] ?? null,
    dark: /bg-\[#0a111a\]|bg-brand-ink|ctc-ig/.test(open),
    heading: heading ? text(heading) : null,
    paragraphs: faq.length > 0 ? [] : paragraphs,
    bullets: faq.length > 0 ? [] : bullets,
    faq,
    ctas,
    images: tiles.length > 0 ? [] : images,
    tiles,
  });
}

// Las fotos del prototipo se copian junto al contenido: sin ellas, portar una sección deja un
// hueco y el diff visual no prueba nada. Solo las referenciadas — `site/images/` tiene más.
// `astro:assets` y las fotos definitivas del cliente son F7.11.
await mkdir(IMAGE_DIR, { recursive: true });
const copied = new Set();
async function localizeImage(image) {
  const name = path.basename(image.src);
  if (!copied.has(name)) {
    await copyFile(path.join("..", "site", image.src), path.join(IMAGE_DIR, name));
    copied.add(name);
  }
  image.src = `/images/home/${name}`;
}
for (const section of sections) {
  for (const image of section.images) await localizeImage(image);
  for (const tile of section.tiles) await localizeImage(tile.image);
}

await mkdir(path.dirname(OUT), { recursive: true });
await writeFile(OUT, JSON.stringify({ sections }, null, 2) + "\n");

console.log(
  sections
    .map(
      (s, i) =>
        `${String(i + 1).padStart(2)}. ${s.dark ? "oscura" : "clara "} ` +
        `p:${String(s.paragraphs.length).padStart(2)} li:${String(s.bullets.length).padStart(2)} ` +
        `cta:${s.ctas.length} img:${String(s.images.length).padStart(2)}  ${s.heading ?? "(sin titulo)"}`,
    )
    .join("\n"),
);
console.log(`\n${sections.length} secciones -> ${OUT}`);

// Lo descartado se imprime siempre: si mañana alguien afloja el filtro, se ve en el build.
if (dropped.length > 0) {
  console.log(`\nDescartado por ser prueba social de la referencia (D-P3): ${dropped.length}`);
  for (const item of dropped) console.log(`  - ${item}`);
}
