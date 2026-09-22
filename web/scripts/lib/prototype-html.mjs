/**
 * Lo común entre los extractores del prototipo (`extract-home.mjs`, `extract-arrival-guide.mjs`,
 * F7.6 y F7.9): limpiar entidades, quitar etiquetas conservando o no el énfasis, y separar el
 * `<body>` en sus `<section>`.
 */

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
export function clean(value) {
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
export function text(fragment) {
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
export function rich(fragment) {
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

export function all(pattern, source) {
  return [...source.matchAll(pattern)];
}

/**
 * Quita del HTML el primer bloque `<div class="${marker}...">...</div>` que encuentre,
 * contando aperturas y cierres de `<div` para no cortar a medias — a diferencia de
 * `splitSections`, aquí si hace falta llevar la cuenta, porque el bloque que se quita vive
 * *adentro* de una sección más grande, no delimita una sección completa.
 *
 * Sirve para sacar tarjetas promocionales incrustadas a la mitad de una sección de texto (el
 * promo del velero de $100 dentro de la sección del aeropuerto de SJD, ver `extract-home.mjs`):
 * sin esto, sus párrafos y su lista de bullets se cuelan como si fueran prosa de la sección que
 * los envuelve.
 */
export function stripBlock(html, marker) {
  const start = html.indexOf(`<div class="${marker}`);
  if (start === -1) return html;
  let depth = 0;
  let cursor = start;
  while (cursor < html.length) {
    const nextOpen = html.indexOf("<div", cursor);
    const nextClose = html.indexOf("</div>", cursor);
    if (nextClose === -1) break;
    if (nextOpen !== -1 && nextOpen < nextClose) {
      depth += 1;
      cursor = nextOpen + 4;
    } else {
      depth -= 1;
      cursor = nextClose + 6;
      if (depth === 0) return html.slice(0, start) + html.slice(cursor);
    }
  }
  return html;
}

/**
 * Separa el `<body>` en secciones, cortando en cada `<section` — igual que antes — pero
 * limitado a lo que hay antes del `<footer>`, no hasta el final del documento.
 *
 * Cortar en cada `<section`, sin importar si anida o no, es justo lo que hace falta aquí: el
 * "promo de velero" del home vive **anidado** dentro de la sección "tours, boats and
 * activities" (un `<section>` sin cerrar en el HTML generado del prototipo — no es el único
 * tag mal cerrado que se ha encontrado). Cortar por la apertura de cada `<section>`, en vez de
 * emparejarla con su cierre, separa igual esos dos bloques en dos entradas — que es lo que se
 * quiere, uno por unidad de contenido — sin necesidad de un parser HTML de verdad que resuelva
 * el anidamiento roto.
 *
 * Lo único que ese método no resuelve solo es la ÚLTIMA sección: al no haber una siguiente
 * `<section` que la corte, se queda con todo lo que sigue —el `<footer>` completo, scripts,
 * estilos—. En `index.html` la última sección real es el FAQ, cuyo extractor ya descarta
 * párrafos y listas sueltas, así que la fuga quedaba encubierta ahí por pura coincidencia; en
 * `arrival-guide.html` la última es el CTA final, sin esa protección, y el footer se colaba
 * entero. Por eso el corte real es en el `<footer`, no en el final del `body`.
 *
 * El *último* `<footer`, no el primero: cada reseña de la sección de testimonios trae el suyo
 * (`<blockquote><footer>` es el patrón semántico normal para la firma de una cita), y hay ocho
 * de esos antes de llegar al pie de página real.
 */
export function splitSections(body) {
  const end = body.lastIndexOf("<footer");
  const scope = end === -1 ? body : body.slice(0, end);
  return scope
    .split(/(?=<section\b)/)
    .slice(1)
    .map((chunk) => {
      const openEnd = chunk.indexOf(">");
      return { openTag: chunk.slice(0, openEnd + 1), inner: chunk.slice(openEnd + 1) };
    });
}
