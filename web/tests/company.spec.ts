import { expect, test } from "@playwright/test";

import { toE164 } from "../src/lib/company";

/** F7.5. CI nunca construye contra el backend, así que la conversión del teléfono —la parte
 *  que de verdad se puede romper con un formato distinto— se prueba aparte. */
test.describe("teléfono a E.164", () => {
  for (const [input, expected] of [
    ["+52 (624) 777 1234", "+526247771234"],
    ["624 777 1234", "+6247771234"],
    ["+52-624-777-1234", "+526247771234"],
  ] as const) {
    test(`"${input}" → ${expected}`, () => {
      expect(toE164(input)).toBe(expected);
    });
  }

  test("lo que no alcanza a ser un teléfono queda en null", () => {
    // Sin esto, un dato a medias en la base terminaría como un `tel:` roto en el sitio.
    expect(toE164(null)).toBeNull();
    expect(toE164("")).toBeNull();
    expect(toE164("624 777")).toBeNull();
  });
});
