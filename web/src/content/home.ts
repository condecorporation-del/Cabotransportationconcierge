/** Contenido de la home, extraído del prototipo aprobado por `scripts/extract-home.mjs` (F7.6).
 *  Se regenera, no se edita a mano; la reescritura en la voz de CTC es F9.1. */
import data from "./home.json";

export interface FaqEntry {
  question: string;
  answer: string;
}

export interface HomeImage {
  src: string;
  alt: string;
}

export interface HomeCta {
  label: string;
  href: string;
}

export interface HomeSection {
  id: string | null;
  dark: boolean;
  heading: string | null;
  paragraphs: string[];
  bullets: string[];
  faq: FaqEntry[];
  ctas: HomeCta[];
  images: HomeImage[];
}

export const HOME_SECTIONS: HomeSection[] = data.sections;
