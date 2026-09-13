# ADR-002 — Reglas del motor de precios

**Fecha:** 2026-09-12 · **Estado:** aceptada (tarifas pendientes de aprobación, D-P1) · **Código:** `backend/app/services/pricing.py`

## Contexto
En ClassVIP el precio se calculaba en varios lugares (frontend y backend) y había combos duplicados, tarifas en 0 y hoteles en dos zonas. El WORKPLAN (D8) exige un único motor de precios en el servidor.

## Decisiones

1. **Un solo lugar calcula.** `quote_transfer` y `quote_activity` son la única fuente del precio para la web, el admin, la IA y Stripe. El frontend solo muestra lo que devuelve el servidor.
2. **Vehículo.**
   - Sin elección del cliente: la primera clase activa donde `min_pax ≤ pasajeros ≤ max_pax` (Suburban 1–5, Sprinter 6–14).
   - Con elección: se permite subir de clase (2 personas en Sprinter) si caben; nunca bajar.
   - Más de 14 → `too_many_passengers` ("contáctanos").
3. **Tarifa base.** Zona del hotel × vehículo × tipo de viaje × servicio. Si no existe → `rate_unavailable`.
4. **Extras.**
   - Precio unitario × cantidad, hasta `max_qty`.
   - Se cobran **una vez por reserva**, aunque sea round trip.
   - No se aceptan extras incluidos (kit básico) ni automáticos (recargo nocturno) como pedido manual.
5. **Recargo nocturno.** Se agrega solo si alguna hora del viaje (aterrizaje o pickup) cae en la ventana de `company_settings`. Por defecto 23:00–05:00 (D-P12): la ventana es `[inicio, fin)`, así que 23:00 y 04:59 cobran y 05:00 no. Una sola vez por reserva.
6. **Promociones.**
   - Candidatas: activas, dentro de fechas de viaje (evaluadas con **la fecha del primer tramo**), fechas de compra (hoy, en la zona horaria de la empresa) y usos disponibles.
   - Sin código se aplican solas (ej. SEPTEMBER 10% OFF); con código, sin importar mayúsculas.
   - **Solo la de mayor descuento**, sin acumular.
   - Alcance `transfer_base`: sobre la tarifa base del traslado (extras intactos). Alcance `all`: sobre el subtotal.
   - Porcentaje redondeado al centavo; fijo en centavos. Nunca mayor que la base del alcance.
   - Código inválido o fuera de fechas → `invalid_promo_code`.
7. **Actividades.** Precio por persona del paquete × invitados. Número exacto de actividades distintas. El park fee se informa en `due_on_site_cents` y el depósito en `deposit_cents`; ninguno suma al total.
8. **Impuestos.** `tax_cents = 0` hasta decidir D-P5 (IVA incluido o desglosado).
9. **Errores.** `QuoteError(code, message)` con códigos estables para traducir en la web (EN/ES).

## Ejemplos (catálogo actual)

| Caso | Cálculo | Total |
|---|---|---|
| Cabo San Lucas, 2 personas, ida, 15 oct | Suburban $110 | **$110.00** |
| Mismo viaje con 1 silla de bebé, 15 sep | $110 + $15 = $125; −10% de $110 = −$11 | **$114.00** |
| Corredor, 8 personas, redondo, 15 oct | Sprinter redondo $261 | **$261.00** |
| San José, aterrizaje 23:30, ida, 15 oct | Suburban $90 + recargo nocturno $20 | **$110.00** |
| Crazy Combo, 2 personas | 2 × $125 = $250 (park fee $50 en sitio) | **$250.00** |

## Consecuencias
- Cambiar una tarifa en el admin cambia las cotizaciones nuevas, no las reservas existentes: la reserva congela sus líneas en `booking_items` (se prueba en F3.1).
- Cualquier regla nueva de precio se agrega aquí y en `pricing.py`, con su test.
