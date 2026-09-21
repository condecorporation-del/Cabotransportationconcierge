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

const SOURCE = path.join("..", "site", "index.html");
const OUT = path.join("src", "content", "home.json");
const IMAGE_DIR = path.join("public", "images", "home");

const ENTITIES = {
  quot: '"',
  apos: "'",
  lt: "<",
  gt: ">",
  amp: "&",
  nbsp: " ",
  mdash: "—",
  ndash: "–",
  hellip: "…",
  rsquo: "’",
  lsquo: "‘",
  ldquo: "“",
  rdquo: "”",
};

/** Entidades y espacios, sin tocar etiquetas. */
function clean(value) {
  return value
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
    .replace(/&(\w+);/g, (match, name) => ENTITIES[name] ?? match)
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Texto plano. Las etiquetas se quitan sin dejar espacio en su lugar: reemplazarlas por " "
 * convierte `<strong>SJD</strong>.` en "SJD ." con el espacio colgando antes del punto.
 */
function text(fragment) {
  return clean(
    fragment
      .replace(/<!--.*?-->/gs, "")
      .replace(/<br\s*\/?>/gi, " ")
      .replace(/<[^>]+>/g, ""),
  );
}

/**
 * Igual, pero conserva `<strong>` y `<em>`: en el prototipo marcan datos (el aeropuerto, el
 * tipo de servicio), no decoran.
 *
 * El centinela tiene que ser algo que no pueda aparecer en el texto. Un número entre espacios
 * no sirve: "up to 10 guests" se rompería.
 */
function rich(fragment) {
  const held = [];
  const masked = fragment
    .replace(/<!--.*?-->/gs, "")
    .replace(/<(\/?)(strong|em|b|i)\b[^>]*>/gi, (_, slash, tag) => {
      const name = /^(b)$/i.test(tag) ? "strong" : /^(i)$/i.test(tag) ? "em" : tag.toLowerCase();
      held.push(`<${slash}${name}>`);
      return `@@${held.length - 1}@@`;
    })
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/<[^>]+>/g, "");
  return clean(masked).replace(/@@(\d+)@@/g, (_, index) => held[Number(index)]);
}

function all(pattern, source) {
  return [...source.matchAll(pattern)];
}

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
const body = html.slice(html.indexOf("<body"));

const sections = [];
for (const chunk of body.split(/(?=<section\b)/).slice(1)) {
  const open = chunk.match(/<section([^>]*)>/)?.[1] ?? "";
  const heading = chunk.match(/<h[12][^>]*>(.*?)<\/h[12]>/s)?.[1];

  // La sección de testimonios es prueba social de la referencia de punta a punta: no se filtra
  // frase por frase, se quita entera (D-P3). Vuelve en F16.1 con las reseñas reales de CTC.
  if (/id="testimonials"/.test(open)) {
    dropped.push("(la sección de testimonios completa)");
    continue;
  }

  const paragraphs = all(/<p[^>]*>(.*?)<\/p>/gs, chunk)
    .map((m) => rich(m[1]))
    .filter(
      (p) => p.replace(/<[^>]+>/g, "").length > 40 && !isWidgetChrome(p) && !isReferenceClaim(p),
    );

  const bullets = all(/<li[^>]*>(.*?)<\/li>/gs, chunk)
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
