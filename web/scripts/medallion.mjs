/**
 * Recorta el medallón oficial de CTC a un PNG circular con fondo transparente (F7.4).
 *
 * El archivo que entregó Marlon es un JPEG cuadrado: el medallón dorado en el centro y, en las
 * esquinas, hojas de palma sobre negro. Esas esquinas no sirven —sobre el obsidiana del sitio
 * se verían como un recuadro— así que hay que encontrar el aro y recortar a su círculo.
 *
 * El aro es lo más dorado de la imagen y lo más externo, así que el recuadro que contiene todos
 * los píxeles dorados es el aro. No se codifican coordenadas a mano: si algún día llega un
 * archivo nuevo del logo, este script vuelve a encontrarlas.
 *
 * Los tamaños del sitio los genera `astro:assets` a partir de este PNG; aquí solo se produce el
 * original limpio. El favicon (recorte del monograma) y el SVG vectorial son F7.16.
 *
 *   npm run medallion
 */
import { mkdir } from "node:fs/promises";
import path from "node:path";

import sharp from "sharp";

const SOURCE = path.join("..", "site", "Cabotransportation logo.jpg");
const OUT_DIR = path.join("src", "assets");
const OUT = path.join(OUT_DIR, "ctc-medallion.png");
const SIZE = 1024;

const image = sharp(SOURCE);
const { width, height } = await image.metadata();
const { data, info } = await image.raw().toBuffer({ resolveWithObject: true });

/** Dorado: claro, cálido y con el rojo bien por encima del azul. */
function isGold(r, g, b) {
  return r > 110 && g > 80 && b < 130 && r - b > 45;
}

let top = height;
let left = width;
let right = -1;
let bottom = -1;

for (let y = 0; y < height; y += 1) {
  for (let x = 0; x < width; x += 1) {
    const i = (y * width + x) * info.channels;
    if (!isGold(data[i], data[i + 1], data[i + 2])) continue;
    if (x < left) left = x;
    if (x > right) right = x;
    if (y < top) top = y;
    if (y > bottom) bottom = y;
  }
}

if (right < 0) throw new Error("No se encontró nada dorado: ¿cambió el archivo del logo?");

// Un cuadrado centrado en el aro: el recuadro dorado puede salir un pixel más ancho que alto.
const centerX = Math.round((left + right) / 2);
const centerY = Math.round((top + bottom) / 2);
const side = Math.max(right - left, bottom - top) + 1;
const half = Math.floor(side / 2);
const crop = {
  left: Math.max(0, centerX - half),
  top: Math.max(0, centerY - half),
  width: Math.min(side, width - Math.max(0, centerX - half)),
  height: Math.min(side, height - Math.max(0, centerY - half)),
};

const mask = Buffer.from(
  `<svg width="${SIZE}" height="${SIZE}"><circle cx="${SIZE / 2}" cy="${SIZE / 2}" r="${SIZE / 2}" fill="#fff"/></svg>`,
);

await mkdir(OUT_DIR, { recursive: true });
await sharp(SOURCE)
  .extract(crop)
  .resize(SIZE, SIZE, { fit: "fill" })
  .composite([{ input: mask, blend: "dest-in" }])
  .png({ compressionLevel: 9 })
  .toFile(OUT);

console.log(`aro detectado en ${left},${top} → ${right},${bottom} (${side} px)`);
console.log(`medallón recortado en ${OUT}`);
