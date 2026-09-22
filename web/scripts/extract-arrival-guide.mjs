/**
 * Saca el contenido de `/arrival-guide` del prototipo aprobado (F7.9).
 *
 * A diferencia de la home (F7.6), esta página tiene solo 5 secciones y cada una tiene una forma
 * distinta — un objeto con nombre por sección es más simple y más claro aquí que forzarlas
 * todas al mismo molde genérico de `extract-home.mjs`.
 *
 * D-P6: el video de esta página en la referencia muestra a *su* anfitriona y *su* letrero. El
 * prototipo ya resolvió eso antes de esta tarea — no hay ningún `<video>` en el HTML, solo un
 * poster propio (`sprinter-interior.jpg`) — así que aquí no hay nada que filtrar, solo portar.
 *
 *   npm run extract:arrival-guide
 */
import { copyFile, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { rich, splitSections, text } from "./lib/prototype-html.mjs";

const SOURCE = path.join("..", "site", "arrival-guide.html");
const OUT = path.join("src", "content", "arrival.json");
const IMAGE_DIR = path.join("public", "images", "arrival-guide");

const html = await readFile(SOURCE, "utf8");
const body = html.slice(html.indexOf("<body"));
const [hero, videoGuide, beAware, steps, cta] = splitSections(body).map((s) => s.inner);

async function localizeImage(src, alt) {
  const name = path.basename(src);
  await mkdir(IMAGE_DIR, { recursive: true });
  await copyFile(path.join("..", "site", src), path.join(IMAGE_DIR, name));
  return { src: `/images/arrival-guide/${name}`, alt: text(alt) };
}

function image(html) {
  const src = html.match(/<img\b[^>]*\ssrc="([^"]*)"/)?.[1];
  const alt = html.match(/<img\b[^>]*\salt="([^"]*)"/)?.[1] ?? "";
  if (!src) throw new Error("Se esperaba una <img> y no apareció ninguna.");
  return localizeImage(src, alt);
}

// `<p\b`, no `<p[^>]*>` a secas: sin el límite de palabra, "<p" hace match con el arranque de
// cualquier otra etiqueta que empiece con esa letra (un `<path>` de un ícono SVG, por ejemplo),
// y el resto de la búsqueda sigue de largo hasta el primer `</p>` real. En esta misma página el
// ícono de alerta de "Be Aware" tiene un `<path>` antes del `<p>` de verdad — sin el límite de
// palabra, el párrafo salía como "Be Aware Kindly inform us..." con el título duplicado dentro.
function paragraph(html) {
  return text(html.match(/<p\b[^>]*>(.*?)<\/p>/s)?.[1] ?? "");
}

function richParagraph(html) {
  return rich(html.match(/<p\b[^>]*>(.*?)<\/p>/s)?.[1] ?? "");
}

const data = {
  hero: {
    // El "<br><span class=italic>" del prototipo separa el nombre de la empresa del resto del
    // título en dos líneas con la segunda en cursiva; se conserva como <em> para que el
    // componente decida cómo partirlo, igual que `rich()` conserva <strong>/<em> en la home.
    eyebrow: text(hero.match(/<div[^>]*px-6[^>]*>(.*?)<\/div>/s)?.[1] ?? ""),
    heading: rich(
      (hero.match(/<h1[^>]*>(.*?)<\/h1>/s)?.[1] ?? "")
        .replace(/<br\s*\/?>/gi, " ")
        .replace(/<span[^>]*>/gi, "<em>")
        .replace(/<\/span>/gi, "</em>"),
    ),
    lede: paragraph(hero),
    poster: await image(hero),
  },
  videoGuide: {
    kicker: text(videoGuide.match(/<span[^>]*>(.*?)<\/span>/s)?.[1] ?? ""),
    heading: text(videoGuide.match(/<h2[^>]*>(.*?)<\/h2>/s)?.[1] ?? ""),
    body: paragraph(videoGuide),
    poster: await image(videoGuide),
  },
  beAware: {
    heading: text(beAware.match(/<h2[^>]*>(.*?)<\/h2>/s)?.[1] ?? ""),
    body: paragraph(beAware),
  },
  steps: {
    kicker: text(steps.match(/<span[^>]*>(.*?)<\/span>/s)?.[1] ?? ""),
    heading: text(steps.match(/<h2[^>]*>(.*?)<\/h2>/s)?.[1] ?? ""),
    intro: paragraph(steps),
    items: [...steps.matchAll(/<article\b[^>]*>(.*?)<\/article>/gs)].map(([, article]) => ({
      title: text(article.match(/<h3[^>]*>(.*?)<\/h3>/s)?.[1] ?? ""),
      body: richParagraph(article),
    })),
    // La tarjeta destacada después de los pasos ("Look for the checkpoint"): mismo contenido
    // que el paso 4, en otras palabras, a modo de resumen. Se porta tal cual llegue a F9.1.
    highlight: (() => {
      const block = steps.match(/mt-16[^]*$/)?.[0] ?? "";
      return {
        title: text(block.match(/<h3[^>]*>(.*?)<\/h3>/s)?.[1] ?? ""),
        body: richParagraph(block),
      };
    })(),
  },
  cta: {
    heading: text(cta.match(/<h2[^>]*>(.*?)<\/h2>/s)?.[1] ?? ""),
    // El link interno a "dónde está Cabo" apunta a `href="#"` en el prototipo — la página de
    // geografía no existe todavía (es contenido de F9). Enlazar a "#" no llevaría a ningún
    // lado; se prefiere el texto plano a un enlace que no hace nada.
    body: paragraph(cta),
    cta: {
      label: text(cta.match(/<a\b[^>]*bg-\[#FFC107\][^>]*>(.*?)<\/a>/s)?.[1] ?? ""),
      href: cta.match(/<a\b[^>]*bg-\[#FFC107\][^>]*\shref="([^"]*)"/)?.[1] ?? "#",
    },
  },
};

await mkdir(path.dirname(OUT), { recursive: true });
await writeFile(OUT, JSON.stringify(data, null, 2) + "\n");

console.log(`hero: "${data.hero.eyebrow}" — ${data.hero.poster.src}`);
console.log(`video-guide: "${data.videoGuide.heading}" — ${data.videoGuide.poster.src}`);
console.log(`be-aware: "${data.beAware.heading}" — "${data.beAware.body.slice(0, 40)}..."`);
console.log(`steps: "${data.steps.heading}", ${data.steps.items.length} pasos`);
console.log(`cta: "${data.cta.heading}" -> ${data.cta.cta.href}`);
console.log(`\narrival-guide.json -> ${OUT}`);
