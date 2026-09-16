/**
 * Los datos de catálogo que la home necesita —zonas y flota—, sacados del catálogo real (F7.6).
 *
 * El prototipo trae los nombres y precios de la referencia; CTC tiene los suyos (§3.5.6) y sus
 * tarifas viven en `backend/scripts/data/catalog.json`, que es la fuente canónica. Se porta la
 * *composición* de las tarjetas y se rellena con datos propios.
 *
 * Lo que queda aquí es el respaldo: cuando el build corre con `CTC_API_URL`, los precios salen
 * de la API y son los vigentes. Sin backend a la vista (CI), se usan estos.
 *
 *   npm run extract:catalog
 */
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const CATALOG = path.join("..", "backend", "scripts", "data", "catalog.json");
const OUT = path.join("src", "content", "catalog.json");

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

/** El más barato de una zona o de un vehículo, para el "desde" de las tarjetas. */
function cheapest(match) {
  const prices = catalog.rates.filter(match).map((rate) => rate.price_cents);
  return prices.length > 0 ? Math.min(...prices) : null;
}

const zones = HOME_ZONES.map((slug, index) => {
  const zone = bySlug.get(slug);
  if (!zone) throw new Error(`La zona ${slug} ya no está en el catálogo.`);

  return {
    slug,
    name: zone.name,
    driveMinutesMin: zone.drive_minutes_min,
    driveMinutesMax: zone.drive_minutes_max,
    // "Starting from" del prototipo es ida y vuelta desde el aeropuerto.
    fromPriceCents: cheapest(
      (rate) =>
        rate.zone === slug && rate.trip_type === "round_trip" && rate.service_scope === "airport",
    ),
    photo: `/images/home/zone-${index + 1}-960.webp`,
  };
});

// La flota: el prototipo dibujaba estas tarjetas con JavaScript, así que su HTML estático no
// trae ninguna. No hay nada que portar — se arman con los datos reales. Las fotos por vehículo
// tampoco existen todavía; llegan con las definitivas del cliente en F7.11.
const vehicles = catalog.vehicle_classes
  .slice()
  .sort((a, b) => a.sort - b.sort)
  .map((vehicle) => ({
    code: vehicle.code,
    name: vehicle.name,
    maxPax: vehicle.max_pax,
    maxBags: vehicle.max_bags,
    fromPriceCents: cheapest(
      (rate) =>
        rate.vehicle_class === vehicle.code &&
        rate.trip_type === "one_way" &&
        rate.service_scope === "airport",
    ),
  }));

await mkdir(path.dirname(OUT), { recursive: true });
await writeFile(OUT, JSON.stringify({ zones, vehicles }, null, 2) + "\n");

const price = (cents) => (cents === null ? "sin tarifa" : `$${cents / 100}`);
for (const zone of zones) {
  console.log(
    `${zone.slug.padEnd(30)} ${String(zone.name.en).padEnd(34)} ` +
      `${price(zone.fromPriceCents).padStart(9)}  ${zone.driveMinutesMin}-${zone.driveMinutesMax} min`,
  );
}
for (const vehicle of vehicles) {
  console.log(
    `${vehicle.code.padEnd(30)} ${vehicle.name.padEnd(34)} ` +
      `${price(vehicle.fromPriceCents).padStart(9)}  ${vehicle.maxPax} pax / ${vehicle.maxBags} maletas`,
  );
}
console.log(`\n${zones.length} zonas y ${vehicles.length} vehiculos -> ${OUT}`);
