/** Contenido de `/arrival-guide`, extraído del prototipo aprobado por
 *  `scripts/extract-arrival-guide.mjs` (F7.9). Se regenera, no se edita a mano. */
import data from "./arrival.json";

export interface ArrivalImage {
  src: string;
  alt: string;
}

export interface ArrivalStep {
  title: string;
  body: string;
}

export interface ArrivalContent {
  hero: {
    eyebrow: string;
    heading: string;
    lede: string;
    poster: ArrivalImage;
  };
  videoGuide: {
    kicker: string;
    heading: string;
    body: string;
    poster: ArrivalImage;
  };
  beAware: {
    heading: string;
    body: string;
  };
  steps: {
    kicker: string;
    heading: string;
    intro: string;
    items: ArrivalStep[];
    highlight: ArrivalStep;
  };
  cta: {
    heading: string;
    body: string;
    cta: { label: string; href: string };
  };
}

export const ARRIVAL: ArrivalContent = data;
