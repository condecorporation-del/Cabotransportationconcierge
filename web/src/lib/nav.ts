/**
 * Estructura del menú (§3.5.2), separada de la plantilla (F7.4).
 *
 * Los destinos son los mismos que los de la referencia; la composición visual es la de §3.5.6 y
 * vive en `SiteHeader.astro`. Los slugs son propios y no llevan prefijo de idioma: `localize()`
 * lo agrega, para que las dos versiones compartan ruta y el `hreflang` cuadre solo (D15).
 */
import type { Locale } from "./site";

export interface NavLink {
  label: string;
  href: string;
  note?: string;
}

export interface MegaColumn {
  title: string;
  links: NavLink[];
}

/** `/precios` en español no: mismo slug en los dos idiomas, solo cambia el prefijo (D15). */
export function localize(href: string, locale: Locale): string {
  if (locale === "en") return href;
  return href === "/" ? "/es/" : `/es${href}`;
}

const EN = {
  services: "Services",
  tours: "All Tours",
  prices: "Prices",
  about: "About Us",
  faq: "FAQ",
  guide: "Travel Guide",
  contact: "Contact",
  reserve: "Reserve",
  myTrip: "My Trip",
  menu: "Menu",
  close: "Close",
  columns: [
    {
      title: "Airport & Transfers",
      links: [
        { label: "All Cabo Transfers", href: "/cabo-transportation" },
        { label: "Hotel Shuttles", href: "/los-cabos-hotel-shuttles" },
        { label: "Private Chauffeur", href: "/private-bilingual-driver" },
        { label: "Activity transfers", href: "/activity-transfers" },
        { label: "Prices & Rates", href: "/cabo-shuttle-prices" },
      ],
    },
    {
      title: "Events & Groups",
      links: [
        { label: "Weddings", href: "/weddings" },
        { label: "Bachelorette & Bachelor Parties", href: "/bachelorette-party-transportation" },
        { label: "Bisbee's Black & Blue", href: "/bisbees-black-and-blue-transportation" },
        { label: "Group Transportation", href: "/group-transfers" },
        { label: "Family Transportation", href: "/family-transportation" },
        { label: "Limousines", href: "/limousines" },
      ],
    },
    {
      title: "Tours",
      links: [
        { label: "City Tours", href: "/city-tours" },
        { label: "Sightseeing Tours", href: "/sightseeing" },
      ],
    },
  ] satisfies MegaColumn[],
  featured: {
    title: "See Cabo with a private driver",
    body: "A Suburban, a bilingual chauffeur and the whole day at your pace.",
    cta: "Reserve a chauffeur",
    href: "/private-bilingual-driver",
  },
  guides: [
    {
      label: "Flight Status",
      href: "/cabo-airport-flights",
      note: "Live SJD arrivals & departures",
    },
    { label: "Uber in Cabo Guide", href: "/is-there-uber-in-cabo" },
    { label: "Taxi at SJD Airport", href: "/cabo-airport-taxi" },
    { label: "Customer reviews", href: "/reviews" },
  ] satisfies NavLink[],
};

const ES: typeof EN = {
  services: "Servicios",
  tours: "Tours",
  prices: "Tarifas",
  about: "Nosotros",
  faq: "Preguntas",
  guide: "Guía de viaje",
  contact: "Contacto",
  reserve: "Reservar",
  myTrip: "Mi viaje",
  menu: "Menú",
  close: "Cerrar",
  columns: [
    {
      title: "Aeropuerto y traslados",
      links: [
        { label: "Todos los traslados", href: "/cabo-transportation" },
        { label: "Traslados de hotel", href: "/los-cabos-hotel-shuttles" },
        { label: "Chofer privado", href: "/private-bilingual-driver" },
        { label: "Traslados a actividades", href: "/activity-transfers" },
        { label: "Precios y tarifas", href: "/cabo-shuttle-prices" },
      ],
    },
    {
      title: "Eventos y grupos",
      links: [
        { label: "Bodas", href: "/weddings" },
        { label: "Despedidas de soltera y soltero", href: "/bachelorette-party-transportation" },
        { label: "Bisbee's Black & Blue", href: "/bisbees-black-and-blue-transportation" },
        { label: "Transporte de grupos", href: "/group-transfers" },
        { label: "Transporte familiar", href: "/family-transportation" },
        { label: "Limusinas", href: "/limousines" },
      ],
    },
    {
      title: "Tours",
      links: [
        { label: "Tours por la ciudad", href: "/city-tours" },
        { label: "Tours panorámicos", href: "/sightseeing" },
      ],
    },
  ],
  featured: {
    title: "Conoce Los Cabos con chofer privado",
    body: "Una Suburban, un chofer bilingüe y el día entero a tu ritmo.",
    cta: "Reservar chofer",
    href: "/private-bilingual-driver",
  },
  guides: [
    {
      label: "Estado de vuelos",
      href: "/cabo-airport-flights",
      note: "Llegadas y salidas de SJD en vivo",
    },
    { label: "¿Hay Uber en Cabo?", href: "/is-there-uber-in-cabo" },
    { label: "Taxi en el aeropuerto", href: "/cabo-airport-taxi" },
    { label: "Reseñas de clientes", href: "/reviews" },
  ],
};

export const NAV = { en: EN, es: ES } as const;

/** Los links que van a la izquierda y a la derecha del medallón (§3.5.6). */
export function sideLinks(locale: Locale): { left: NavLink[]; right: NavLink[] } {
  const t = NAV[locale];
  return {
    left: [
      { label: t.tours, href: localize("/tours", locale) },
      { label: t.prices, href: localize("/cabo-shuttle-prices", locale) },
    ],
    right: [
      { label: t.about, href: localize("/about", locale) },
      { label: t.faq, href: localize("/faq", locale) },
      { label: t.guide, href: localize("/travel-guide", locale) },
      { label: t.contact, href: localize("/contact", locale) },
    ],
  };
}
