/**
 * Datos del sitio en un solo lugar (F7.3).
 *
 * Los de contacto siguen siendo **placeholder** a propósito: salen de `company_settings` y
 * Marlon todavía no los entrega (D-P4, `docs/content/checklist-cliente.md`). La regla del plan
 * es que se vean como placeholder y que producción quede bloqueada hasta tenerlos — por eso
 * están marcados aquí y no repartidos por las plantillas.
 */

export const SITE = {
  name: "Cabo Transportation Concierge",
  shortName: "CTC",
  url: "https://www.cabotransportationconcierge.com",
  locales: ["en", "es"] as const,
  defaultLocale: "en",
} as const;

export type Locale = (typeof SITE.locales)[number];

/**
 * Lo que se muestra mientras `company_settings` no tenga datos reales (D-P4). No es un teléfono
 * al que se pueda llamar: `company.ts` lo marca como provisional y nada del sitio lo publica
 * como enlace `tel:` ni `wa.me`.
 */
export const CONTACT = {
  phone: "+52 (624) 000 0000",
} as const;

/**
 * Diccionario de UI (D15). El inglés define las claves y el español debe traerlas todas: si
 * falta una, el build falla aquí en vez de dejar un hueco en la página.
 */
const EN = {
  skipToContent: "Skip to content",
  whatsapp: "Chat on WhatsApp",
  customerHelp: "Customer Help",
  footerRights: "All rights reserved.",
  contactPending: "Contact details coming soon",
  footerGuides: "Travel Guide",
  hours: "7:00 AM – 9:00 PM · Mon–Sun",
  cancellationPolicy: "Free cancellation up to {hours} h before pickup",
  changePolicy: "Free changes up to {hours} h before pickup",
} as const;

export type UiKey = keyof typeof EN;

const ES: Record<UiKey, string> = {
  skipToContent: "Saltar al contenido",
  whatsapp: "Escríbenos por WhatsApp",
  customerHelp: "Ayuda al cliente",
  footerRights: "Todos los derechos reservados.",
  contactPending: "Datos de contacto por confirmar",
  footerGuides: "Guía de viaje",
  hours: "7:00 AM – 9:00 PM · Lun–Dom",
  cancellationPolicy: "Cancelación gratis hasta {hours} h antes de la recogida",
  changePolicy: "Cambios gratis hasta {hours} h antes de la recogida",
};

export const UI: Record<Locale, Record<UiKey, string>> = { en: EN, es: ES };

/** URL absoluta a partir de una ruta del sitio; la usan el canonical y las etiquetas OG. */
export function absoluteUrl(path: string): string {
  return new URL(path, SITE.url).href;
}
