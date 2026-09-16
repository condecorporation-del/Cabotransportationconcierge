/**
 * Las zonas de la home (F7.6).
 *
 * `src/content/zones.json` lo genera `scripts/extract-zones.mjs` del catálogo canónico y es el
 * respaldo. Si el build corre con `CTC_API_URL`, los precios se refrescan contra la API, que es
 * la que sabe la tarifa vigente — el admin puede haberla cambiado desde F6.12.
 */
import data from "../content/zones.json";

export interface Zone {
  slug: string;
  name: Record<string, string>;
  driveMinutesMin: number;
  driveMinutesMax: number;
  fromPriceCents: number | null;
  photo: string;
}

const BUNDLED: Zone[] = data.zones;

async function livePrices(): Promise<Map<string, number | null>> {
  const base = process.env["CTC_API_URL"];
  if (!base) return new Map();

  const response = await fetch(new URL("/api/v1/catalog/zones", base));
  if (!response.ok) {
    throw new Error(`El backend respondió ${response.status} al pedir las zonas.`);
  }
  const zones = (await response.json()) as { slug: string; from_price_cents: number | null }[];
  return new Map(zones.map((zone) => [zone.slug, zone.from_price_cents]));
}

let cached: Promise<Zone[]> | undefined;

export function getHomeZones(): Promise<Zone[]> {
  cached ??= livePrices().then((prices) =>
    BUNDLED.map((zone) => ({
      ...zone,
      fromPriceCents: prices.get(zone.slug) ?? zone.fromPriceCents,
    })),
  );
  return cached;
}

/** 16000 → "$160". Las tarifas del catálogo son siempre dólares enteros. */
export function money(cents: number): string {
  return `$${Math.round(cents / 100).toLocaleString("en-US")}`;
}
