/**
 * Baja las fuentes de marca de Google Fonts a `public/fonts/` y escribe sus `@font-face`.
 *
 * Se auto-hospedan a propósito (§3.5.6 y F7.15): así el primer pantallazo no depende de un
 * tercero, no hay una conexión extra que abrir antes de pintar texto, y nada del visitante
 * viaja a Google. Solo se guardan los subconjuntos `latin` y `latin-ext` — los que cubren
 * inglés y español con acentos y ñ; el resto (cirílico, vietnamita) sobra y pesa.
 *
 * Las tres familias son SIL Open Font License 1.1, que permite auto-hospedarlas.
 *
 *   node scripts/fonts.mjs
 */
import { mkdir, readdir, rm, writeFile } from "node:fs/promises";
import path from "node:path";

const FAMILIES = [
  "Cormorant+Garamond:ital,wght@0,500;0,600;0,700;1,600",
  "Cinzel:wght@500;600",
  "Manrope:wght@400;500;700",
];
const SUBSETS = new Set(["latin", "latin-ext"]);
const OUT_DIR = path.join("public", "fonts");
const FACES_FILE = path.join("src", "styles", "fonts.css");

// Sin un User-Agent moderno, Google responde con `truetype` en vez de WOFF2.
const CHROME =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) " +
  "Chrome/131.0.0.0 Safari/537.36";

const url = `https://fonts.googleapis.com/css2?${FAMILIES.map((f) => `family=${f}`).join("&")}&display=swap`;
const css = await (await fetch(url, { headers: { "User-Agent": CHROME } })).text();

await rm(OUT_DIR, { recursive: true, force: true });
await mkdir(OUT_DIR, { recursive: true });

// El comentario con el subconjunto va ANTES de su `@font-face`, así que hay que tomar el par
// junto: cortar por `@font-face` deja cada bloque con la etiqueta del siguiente.
const blocks = css.matchAll(/\/\*\s*([\w-]+)\s*\*\/\s*@font-face\s*\{([^}]*)\}/g);
const faces = [];

for (const [, subset, block] of blocks) {
  if (!SUBSETS.has(subset)) continue;

  const family = block.match(/font-family:\s*'([^']+)'/)?.[1];
  const style = block.match(/font-style:\s*(\w+)/)?.[1] ?? "normal";
  const weight = block.match(/font-weight:\s*(\d+)/)?.[1] ?? "400";
  const range = block.match(/unicode-range:\s*([^;]+);/)?.[1];
  const src = block.match(/url\((https:[^)]+\.woff2)\)/)?.[1];
  if (!family || !src || !range) continue;

  const slug = family.toLowerCase().replace(/\s+/g, "-");
  const name = `${slug}-${weight}${style === "italic" ? "-italic" : ""}-${subset}.woff2`;
  const bytes = Buffer.from(
    await (await fetch(src, { headers: { "User-Agent": CHROME } })).arrayBuffer(),
  );
  await writeFile(path.join(OUT_DIR, name), bytes);

  faces.push(
    `@font-face {\n` +
      `  font-family: "${family}";\n` +
      `  font-style: ${style};\n` +
      `  font-weight: ${weight};\n` +
      `  font-display: swap;\n` +
      `  src: url("/fonts/${name}") format("woff2");\n` +
      `  unicode-range: ${range};\n` +
      `}`,
  );
}

const header =
  "/* Generado por `node scripts/fonts.mjs` — no editar a mano.\n" +
  "   Cormorant Garamond, Cinzel y Manrope, SIL Open Font License 1.1 (§3.5.6, F7.2). */\n\n";
await writeFile(FACES_FILE, header + faces.join("\n\n") + "\n");

const files = await readdir(OUT_DIR);
console.log(
  `${files.length} archivos WOFF2 en ${OUT_DIR}, ${faces.length} @font-face en ${FACES_FILE}`,
);
