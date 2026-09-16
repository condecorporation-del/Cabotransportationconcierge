import { useState } from "react";

/** Isla mínima de F7.1: existe para probar que la hidratación de React funciona de punta a
 *  punta. La reemplazan las islas de verdad (cotizador, reserva) en F7.6 y F8. */
export default function BuildStamp() {
  const [hydrated, setHydrated] = useState(false);
  return (
    <button
      type="button"
      onClick={() => setHydrated(true)}
      className="rounded border border-neutral-400 px-4 py-2 text-sm"
    >
      {hydrated ? "React hidratado" : "Probar la isla de React"}
    </button>
  );
}
