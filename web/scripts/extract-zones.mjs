/**
 * Las cinco zonas que el prototipo muestra en la home, sacadas del catálogo real (F7.6).
 *
 * El prototipo trae los nombres y precios de la referencia; CTC tiene los suyos (§3.5.6) y sus
 * tarifas viven en `backend/scripts/data/catalog.json`, que es la fuente canónica. Se porta la
 * *composición* de las tarjetas y se rellena con datos propios.
 *
 * Lo que queda aquí es el respaldo: cuando el build corre con `CTC_API_URL`, los precios salen
 * de la API y son los vigentes. Sin backend a la vista (CI), se usan estos.
 *
 *   npm run extract:zones
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const CATALOG = path.join("..", "backend", "scripts", "data", "catalog.json");
const OUT = path.join("src", "content", "zones.json");

// Las cinco tarjetas del home, en el orden del prototipo, con la foto que le toca a cada una.
const HOME_ZONES = [
  "san-jose-del-cabo-estuary",
  "the-corridor",
  "cabo-san-lucas-marina",
  "pacific-coast",
  "pacific-north",
];

const catalog = JSON.parse(await readFile(CATALOG, "utf8"));
const bySlug = new Map(catalog.zones.map((zone) => [zone.slug, zone]));

const zones = HOME_ZONES.map((slug, index) => {
  const zone = bySlug.get(slug);
  if (!zone) throw new Error(`La zona ${slug} ya no está en el catálogo.`);

  // "Starting from" del prototipo es ida y vuelta desde el aeropuerto: el más barato de la zona.
  const prices = catalog.rates
    .filter(
      (rate) =>
        rate.zone === slug && rate.trip_type === "round_trip" && rate.service_scope === "airport",
    )
    .map((rate) => rate.price_cents);

  return {
    slug,
    name: zone.name,
    driveMinutesMin: zone.drive_minutes_min,
    driveMinutesMax: zone.drive_minutes_max,
    fromPriceCents: prices.length > 0 ? Math.min(...prices) : null,
    photo: `/images/home/zone-${index + 1}-960.webp`,
  };
});

await mkdir(path.dirname(OUT), { recursive: true });
await writeFile(OUT, JSON.stringify({ zones }, null, 2) + "\n");

for (const zone of zones) {
  const price = zone.fromPriceCents === null ? "sin tarifa" : `$${zone.fromPriceCents / 100}`;
  console.log(
    `${zone.slug.padEnd(30)} ${String(zone.name.en).padEnd(34)} ${price.padStart(9)}  ${zone.driveMinutesMin}-${zone.driveMinutesMax} min`,
  );
}
console.log(`\n${zones.length} zonas -> ${OUT}`);
