/**
 * Datos de la empresa, leídos del backend **en el build** (F7.5).
 *
 * El sitio es estático: esto corre una vez al construir, no en cada visita. Cambiar el teléfono
 * en la base y reconstruir lo actualiza; sin reconstruir, no.
 *
 * Si `CTC_API_URL` no está definida —CI, o un `npm run dev` sin backend levantado— se usa el
 * placeholder de `site.ts` y `pending` se queda en `true`, que es la regla de D-P4: se ve como
 * provisional en vez de inventar un número. `scripts/check-contact.mjs` es el que bloquea el
 * build de producción con datos provisionales.
 */
import type { paths } from "@ctc/api-client/src/schema";

import { CONTACT } from "./site";

type CompanyOut =
  paths["/api/v1/catalog/company"]["get"]["responses"]["200"]["content"]["application/json"];

export interface Company {
  /** `true` mientras los datos sigan siendo el placeholder (D-P4). */
  pending: boolean;
  phone: string | null;
  phoneE164: string | null;
  whatsappE164: string | null;
  offices: Record<string, unknown>;
  socialLinks: Record<string, unknown>;
  cancellationHours: number;
  changeHours: number;
}

const PLACEHOLDER: Company = {
  pending: true,
  phone: CONTACT.phone,
  phoneE164: null,
  whatsappE164: null,
  offices: {},
  socialLinks: {},
  cancellationHours: 24,
  changeHours: 5,
};

/** `+52 (624) 123 4567` → `+526241234567`, que es lo que aceptan `tel:` y `wa.me`. */
export function toE164(value: string | null | undefined): string | null {
  if (!value) return null;
  const digits = value.replace(/\D/g, "");
  return digits.length >= 10 ? `+${digits}` : null;
}

async function fetchCompany(): Promise<Company> {
  const base = process.env["CTC_API_URL"];
  if (!base) return PLACEHOLDER;

  const response = await fetch(new URL("/api/v1/catalog/company", base));
  if (!response.ok) {
    throw new Error(`El backend respondió ${response.status} al pedir los datos de la empresa.`);
  }
  const data = (await response.json()) as CompanyOut;
  const phoneE164 = toE164(data.phone);

  return {
    // Sin teléfono en la base, los datos siguen siendo provisionales aunque el backend responda.
    pending: phoneE164 === null,
    phone: data.phone ?? CONTACT.phone,
    phoneE164,
    whatsappE164: toE164(data.whatsapp)?.replace("+", "") ?? null,
    offices: data.offices ?? {},
    socialLinks: data.social_links ?? {},
    cancellationHours: data.cancellation_hours,
    changeHours: data.change_hours,
  };
}

// Una sola petición por build, aunque la pidan el header y el footer.
let cached: Promise<Company> | undefined;

export function getCompany(): Promise<Company> {
  cached ??= fetchCompany();
  return cached;
}
