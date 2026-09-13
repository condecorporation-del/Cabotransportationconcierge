# ADR-002 — Reglas del motor de precios

**Fecha:** 2026-09-12 (revisado el mismo día para igualar la referencia, WORKPLAN §3.5) · **Estado:** aceptada · **Código:** `backend/app/services/pricing.py`

## Contexto
En ClassVIP el precio se calculaba en varios lugares y había combos duplicados, tarifas en 0 y hoteles en dos zonas. El WORKPLAN (D8) exige un único motor en el servidor. Marlon decidió además que las tarifas y reglas sean **iguales a allwayscabotransportation.com** (D-P1, D-P8, D-P14). Las fórmulas se tomaron de su código de reserva, no solo de lo visible.

## Decisiones

1. **Un solo lugar calcula.** `quote_transfer` y `quote_activity` son la única fuente del precio para la web, el admin, la IA y Stripe.
2. **Catálogo.**
   - 10 zonas con nombres propios de CTC.
   - 5 vehículos: Suburban 5, Escalade 5, Van 10, Limousine 10 (6 incluidos) y Sprinter 17.
   - Tarifas por zona × vehículo × ida/redondo × aeropuerto/local (180 filas). La limusina solo opera en las zonas 1 a 5; en las demás → `rate_unavailable`.
3. **Unidades.**
   - `unidades = ceil(pasajeros / max_pax)`. Nunca se rechaza por capacidad; pasajeros de 1 a 20.
   - Tarifa base = tarifa × unidades.
   - Sin vehículo elegido ("Any type of Vehicle") se toma el de menor total; si hay empate, el de menor `sort`.
4. **Pasajeros extra (limusina).** Si `pasajeros > included_pax × unidades`: `(pasajeros − included_pax × unidades) × unidades × tramos × extra_pax_cents` ($10).
5. **Extras.**
   - Hasta `max_qty`.
   - Las primeras `free_qty` unidades salen en $0 (primera silla de auto y primer booster).
   - Precio por vehículo si existe (parada en súper: $50, $120 en Escalade).
   - `one_per_vehicle`: si se pide, la cantidad debe ser al menos las unidades → `extra_per_vehicle`.
   - Los extras incluidos (agua y cerveza) no se piden.
6. **Recargo nocturno.**
   - Para cada tramo, horas nocturnas de su hora de servicio con la ventana de `company_settings` (23:00–05:00):
     - Los primeros 75 minutos cuentan 1 hora; después, 1 hora más por cada hora iniciada.
     - Ejemplos: 23:00 → 1, 00:15 → 2, 04:59 → 6, 05:00 → 0.
   - Total de horas × `extra_hour_cents` del vehículo (Suburban $85, Escalade $150, Van $110, Sprinter $115, Limousine $195). No se multiplica por unidades.
   - **Diferencia deliberada con la referencia:** en redondo allá solo cuenta el tramo de regreso cuando los dos son nocturnos (un error de su código); aquí se suman los dos tramos.
7. **Promociones.**
   - Candidatas: activas, dentro de fechas de viaje (primer tramo), fechas de compra y usos disponibles.
   - Sin código se aplican solas; con código, sin importar mayúsculas.
   - Solo la de mayor descuento.
   - `transfer_base`: sobre la tarifa base de todas las unidades.
   - Código inválido → `invalid_promo_code`.
8. **IVA y efectivo** (igual a la referencia; el contador de CTC lo confirma antes de producción, D-P5).
   - Tarjeta: `card_tax_percent` (16%) sobre subtotal − descuento.
   - Efectivo: sin IVA, y no se permite en salidas al aeropuerto → `cash_unavailable`.
   - Salida al aeropuerto (hotel → SJD, ida): sin IVA.
   - Depósito con tarjeta al pagar en efectivo: Escalade $100, Limousine $110 (nunca mayor que el total).
9. **Actividades.** Precio por persona del paquete × invitados; park fee en sitio y depósito informados aparte.
10. **Errores.** `QuoteError(code, message)` con códigos estables para traducir en la web.

## Ejemplos (catálogo actual, octubre, efectivo salvo que se indique)

| Caso | Cálculo | Total |
|---|---|---|
| Cabo San Lucas, 2 personas, Suburban, ida | $110 | **$110.00** |
| Igual con tarjeta | $110 + IVA 16% $17.60 | **$127.60** |
| Cabo San Lucas, 8 personas en Suburban | 2 unidades × $110 | **$220.00** |
| Cabo San Lucas, 20 personas, sin elegir vehículo | 2 Vans × $130 (menor total) | **$260.00** |
| Limusina, 8 personas, redondo | $465 + 2 extra × 2 tramos × $10 | **$505.00** |
| San José, aterrizaje 23:30, Suburban, ida | $90 + 1 h × $85 | **$175.00** |
| 2 sillas de auto, Cabo San Lucas, 15 sep | $110 + $0 + $10 = $120; −10% de $110 | **$109.00** |
| Escalade con parada en súper | $165 + $120 | **$285.00** |
| Crazy Combo, 2 personas | 2 × $125 (park fee $50 en sitio) | **$250.00** |

## Consecuencias
- Cambiar una tarifa en el admin cambia las cotizaciones nuevas, no las reservas existentes (`booking_items` congela las líneas).
- La reserva guarda las unidades en `booking_legs.vehicle_count` y el despacho asigna un chofer por unidad (`booking_assignments.unit_index`).
- Cualquier regla nueva de precio se agrega aquí y en `pricing.py`, con su test.
