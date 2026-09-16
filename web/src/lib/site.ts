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

/** Pendiente de D-P4. `pending: true` hace que la plantilla lo muestre como provisional. */
export const CONTACT = {
  pending: true,
  phone: "+52 (624) 000 0000",
  phoneE164: "+526240000000",
  whatsapp: "+52 (624) 000 0000",
  whatsappE164: "526240000000",
  email: "reservations@cabotransportationconcierge.com",
  hours: "7:00 AM – 9:00 PM · Mon–Sun",
} as const;

export const UI: Record<Locale, Record<string, string>> = {
  en: {
    skipToContent: "Skip to content",
    whatsapp: "Chat on WhatsApp",
    customerHelp: "Customer Help",
    footerRights: "All rights reserved.",
    contactPending: "Contact details coming soon",
  },
  es: {
    skipToContent: "Saltar al contenido",
    whatsapp: "Escríbenos por WhatsApp",
    customerHelp: "Ayuda al cliente",
    footerRights: "Todos los derechos reservados.",
    contactPending: "Datos de contacto por confirmar",
  },
};

/** URL absoluta a partir de una ruta del sitio; la usan el canonical y las etiquetas OG. */
export function absoluteUrl(path: string): string {
  return new URL(path, SITE.url).href;
}
