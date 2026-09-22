/**
 * Anchos del poster del hero, compartidos entre `Hero.astro` (el `<Image>` que se ve) y
 * `index.astro` (el `<link rel="preload">` en el `<head>`) — F7.7.
 *
 * Un solo lugar para los dos: si el preload y la imagen real piden anchos distintos, el
 * navegador descarga el archivo dos veces (uno para el preload, otro para el que de verdad usa).
 */
// El salto de 640 a 960 obligaba a un teléfono típico (viewport ~390-430 px, DPR 1.75-3) a
// pedir el escalón de 960, mucho más pesado de lo que su pantalla necesita — Lighthouse mide
// móvil con un ancho efectivo de ~721 px (412 × 1.75). El escalón de 768 le da algo más cercano.
export const HERO_POSTER_WIDTHS = [480, 768, 1024, 1440, 2000] as const;

// El hero mide `w-full`: la imagen siempre llena el ancho del viewport.
export const HERO_POSTER_SIZES = "100vw";
