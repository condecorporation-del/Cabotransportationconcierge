# Bitácora — Cabo Transportation Concierge

Una entrada por sesión o tarea, la más reciente arriba (formato en `AGENTS.md` §10).

## 2026-09-12 — F3.9 auditoría, F3.10 contacto y F3.11 atribución

**Qué se hizo**
- **F3.9:** crear una reserva deja `audit_logs` (`create`, actor `customer`, código, estado, total e IP). Con cambios (`customer_change`) y cancelación (`status_change`), toda mutación pública queda auditada. Un reintento con la misma `Idempotency-Key` no duplica el registro.
- **F3.11:** `attribution` en la solicitud de reserva (`utm_source`, `utm_medium`, `utm_campaign`, `utm_term`, `utm_content`, `referrer`) → `bookings.utm`, solo con los campos presentes.
- **F3.10:** `POST /api/v1/contact` (5/min) → 202.
  - Honeypot `website`: si llega con texto, responde igual pero no guarda.
  - `app/core/turnstile.py`: verifica el token con Cloudflare (timeout 5 s; error de red = verificación fallida). Sin token → 400 `captcha_required`; rechazado → 400 `captcha_failed`.
  - `TURNSTILE_SECRET_KEY` vacía en local = no se exige; **obligatoria en producción** (config fail-fast).
  - El aviso por correo a la empresa llega con la cola de F5.
- `client_ip` en `deps.py` compartido por reservas y contacto. `httpx` pasa a dependencia de ejecución.

**Archivos:** `backend/app/api/deps.py`, `backend/app/api/v1/bookings.py`, `backend/app/api/v1/contact.py`, `backend/app/core/config.py`, `backend/app/core/turnstile.py`, `backend/app/main.py`, `backend/app/schemas/bookings.py`, `backend/app/schemas/contact.py`, `backend/app/services/bookings.py`, `backend/tests/test_booking_state.py`, `backend/tests/test_bookings.py`, `backend/tests/test_config.py`, `backend/tests/test_contact.py`, `backend/.env.example`, `backend/pyproject.toml`, `backend/uv.lock`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **149 passed** (6 nuevos):
  - La reserva guarda la UTM exacta y el registro `create` con su código.
  - El mensaje de contacto se guarda con su página de origen.
  - El honeypot con texto → 202 y ningún mensaje guardado.
  - Con Turnstile configurado y sin token → 400 `captcha_required`, sin guardar.
  - Con configuración de producción: sin token → 400; token aceptado por un Cloudflare simulado → pasa y envía secreto, token e IP; token rechazado → `captcha_failed`.
  - Producción sin `TURNSTILE_SECRET_KEY` no arranca.
- `ruff`, `mypy`, `alembic check`, `pip-audit` y `tsc` → sin errores.

**Pendiente:** F3.8 (voucher PDF).

## 2026-09-12 — F3.7 cambios y cancelación del cliente

**Qué se hizo**
- `app/core/errors.py`: `AppError(code, message)` con `status_code`. `QuoteError` (422) y `TransitionError` (409) heredan de él; un solo handler en `main.py` responde `{"detail": {"code", "message"}}`.
- `PATCH /bookings/{code}` (Bearer): vuelo, aerolínea, hora del vuelo y notas.
  - Solo en `pending_payment`, `offline_hold`, `confirmed` o `paid`; si no → `not_editable`.
  - Hasta `change_hours` antes del pickup (5 h por defecto, D-P2) → si no, `change_window`.
  - Una hora nueva mueve el pickup conservando la anticipación (3 h, 2 h o 0 en llegadas), también si cruza la medianoche.
  - Si la hora nueva entra o sale del recargo nocturno → `price_change` (el precio congelado no se toca).
  - Auditoría `customer_change` con el antes y el después de tramos y notas.
- `POST /bookings/{code}/cancel` (Bearer, motivo opcional):
  - Hasta `cancellation_hours` antes del primer servicio (24 h por defecto) → si no, `cancel_window`.
  - Pasa por la máquina de estados (ya cancelada o completada → 409 `invalid_transition`), deja la auditoría y cancela los tramos. El reembolso llega con F4.
- **Corrección:** las reservas de actividades no guardaban su fecha. Ahora `booking_items.service_date` (migración `43fcd1c0fe04`) y la ventana de cancelación la usa.
- `FlightNumber`: tipo reutilizable con la validación y normalización del vuelo (reserva y cambios).

**Archivos:** `backend/alembic/versions/20260912_43fcd1c0fe04_fecha_de_actividad_en_items_de_reserva.py`, `backend/app/api/v1/bookings.py`, `backend/app/core/errors.py`, `backend/app/main.py`, `backend/app/models/booking.py`, `backend/app/schemas/bookings.py`, `backend/app/schemas/quotes.py`, `backend/app/services/booking_state.py`, `backend/app/services/bookings.py`, `backend/app/services/pricing.py`, `backend/tests/test_booking_changes.py`, `backend/tests/test_bookings.py`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **143 passed** (4 nuevos):
  - Cambio de salida de 11:00 a 12:30 con vuelo `dl 590` → pickup de 08:00 a 09:30, vuelo `DL590`, notas guardadas y auditoría con el pickup anterior.
  - Llegada movida a las 23:30 → `price_change`.
  - Con ventanas de un año → `change_window` y `cancel_window`.
  - Cancelar → `cancelled` con los tramos cancelados; cancelar otra vez → 409; cambiar después → `not_editable`.
  - La actividad guarda su fecha en los ítems.
- `ruff`, `mypy`, `alembic check` y `tsc` → sin errores.

**Pendiente:** F3.8 (voucher PDF), F3.9 (auditoría al crear), F3.10 (contacto), F3.11 (UTM); reembolso al cancelar una reserva pagada (F4).

## 2026-09-12 — F3.5 enlace de gestión firmado y F3.6 My Trip

**Qué se hizo**
- `app/core/security.py`: `booking_token` y `read_booking_token` con itsdangerous (`URLSafeTimedSerializer`, salt `booking-manage`, 90 días). El token lleva empresa y código; uno alterado, expirado o de otra empresa no se puede leer.
- `POST /bookings` ahora devuelve `token` para la página de confirmación (§8.1 paso 6).
- `GET /bookings/{code}` con `Authorization: Bearer <token>` → detalle con tramos, ítems y notas.
  - Sin token, token alterado o expirado → 401 con instrucción para buscar la reserva.
  - Token válido de otra reserva → 404.
- `GET /bookings/lookup?code=&email=` (5/min además del límite general): código sin importar mayúsculas y email sin importar mayúsculas. Si no existe o el email no coincide → el mismo 404 con el mismo cuerpo.
- `rate_limit`: el contador se separa por ruta y por límite, para combinar el general del router con uno más estricto por ruta.
- Config: en local sin `SECRET_KEY` se genera una clave aleatoria por arranque; staging y producción siguen exigiendo 32 caracteres.

**Archivos:** `backend/app/api/v1/bookings.py`, `backend/app/core/config.py`, `backend/app/core/rate_limit.py`, `backend/app/core/security.py`, `backend/app/schemas/bookings.py`, `backend/tests/test_booking_access.py`, `backend/tests/test_bookings.py`, `backend/tests/test_config.py`, `backend/.env.example`, `backend/pyproject.toml`, `backend/uv.lock`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **139 passed** (7 nuevos): el token abre su reserva; token alterado o ausente → 401; token de otra reserva → 404; token emitido hace 90 días y 1 minuto → 401; lookup con código en minúsculas y email en mayúsculas → token que abre la reserva; email incorrecto y reserva inexistente → mismo 404 y mismo cuerpo; la sexta búsqueda en un minuto → 429; clave local aleatoria y distinta en cada arranque.
- `ruff`, `mypy`, `alembic check`, `pip-audit` y `tsc` → sin errores.

**Pendiente:** F3.7 (cambios y cancelación con políticas), F3.8 (voucher PDF), F3.9 (auditoría de creación y cambios).

## 2026-09-12 — F3.2 máquina de estados, F3.3 validaciones y F3.4 recargo nocturno

**Qué se hizo**
- `app/services/booking_state.py`:
  - Tabla `TRANSITIONS` de §8.2 y `transition()`, único lugar donde cambia `bookings.status`.
  - Una transición no listada lanza `TransitionError` (`code = invalid_transition`, pensado para 409).
  - Cada cambio agrega `audit_logs` en la misma transacción (actor, antes, después, motivo, IP). Cancelar fija `cancelled_at` y `cancel_reason`.
- **Validaciones de F3.3** al reservar:
  - Anticipación mínima `company_settings.min_notice_hours` (24 h por defecto; migración `4e2afe533f53`), medida en la zona horaria de la empresa → `too_soon`.
  - Actividades desde mañana → `too_soon`.
  - Hora obligatoria en cada tramo → `time_required`.
  - Vuelo normalizado (`aa 1245` → `AA1245`) y validado: código IATA o ICAO + 1 a 4 dígitos → 422.
  - Regreso después de la llegada, también el mismo día → 422.
  - Pickup de salida 3 h antes de un vuelo internacional o 2 h si es nacional (`international`, por defecto `true`). Si cae el día anterior, la fecha del tramo es la del pickup, para que el despacho lo vea en el día correcto.
- **F3.4:** el recargo nocturno ya lo agrega el motor (F2.1); el test confirma que una llegada a las 23:10 guarda el ítem en la reserva con el mismo total que la cotización.

**Archivos:** `backend/alembic/versions/20260912_4e2afe533f53_anticipacion_minima_para_reservar.py`, `backend/app/models/company.py`, `backend/app/schemas/quotes.py`, `backend/app/services/booking_state.py`, `backend/app/services/bookings.py`, `backend/tests/test_booking_state.py`, `backend/tests/test_bookings.py`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **132 passed** (42 nuevos):
  - Las 36 combinaciones de estados contra la tabla de §8.2, escrita a mano en el test; las no permitidas no cambian el estado.
  - Una cancelación guarda la auditoría con actor, motivo y `cancelled_at`.
  - Pickup 06:00 para un vuelo nacional a las 08:00; 22:30 del día anterior para un internacional a la 01:30.
  - Reserva a 2 h → `too_soon`; sin hora → `time_required`; actividad para hoy → `too_soon`.
  - Vuelo `12345678` o regreso a las 09:00 tras llegar a las 13:20 del mismo día → 422.
  - Llegada 23:10 → `NIGHT_SURCHARGE` y el total de la reserva igual al de la cotización.
- `ruff`, `mypy`, `alembic check` y `tsc` → sin errores.

**Pendiente:** el 409 de `TransitionError` se conecta y se prueba en la API con F3.7 (cancelación del cliente), el primer endpoint que cambia estados.

## 2026-09-12 — F3.1 `POST /bookings` y F2.8 precio congelado

**Qué se hizo**
- `POST /api/v1/bookings` (rate limit 10/min) → 201 con código, estado, montos e ítems.
  - Unión `transfer` | `activity`: la misma solicitud de la cotización más `customer`, `notes` y, en one way, `direction` (`arrival` o `departure`).
  - El servidor vuelve a cotizar con el motor único; el cliente no puede mandar montos (campo desconocido → 422).
  - Todo en una transacción: cliente, reserva `pending_payment`, tramos, ítems con precio congelado y código `CTC-AAAA-NNNNNN`.
- **Idempotencia:** `Idempotency-Key` (8 a 80 caracteres) guardado en `bookings` con índice único parcial por empresa (migración `9c5a8aed60e7`). Un `pg_advisory_xact_lock` por clave forma en fila los POST simultáneos; el segundo devuelve la reserva del primero.
- **Cliente único por email** sin importar mayúsculas (`INSERT ... ON CONFLICT` sobre `lower(email)`). Un dato nuevo completa lo que falta (teléfono, país) pero no pisa el nombre guardado, para que un tercero con el mismo email no altere al cliente.
- **Tramos:** redondo → llegada (SJD → hotel) y salida (hotel → SJD); one way según `direction`. Vuelo y aerolínea por tramo. Traslados locales → `scope_unavailable` (por WhatsApp).
- **Actividades:** sin tramos; el park fee va como ítem `park_fee` informativo, fuera del total.
- `Quote` guarda en privado la promoción aplicada para `bookings.promotion_id` (no sale en la API).
- Nuevas dependencias: `email-validator`. Cliente tipado regenerado.

**Archivos:** `backend/alembic/versions/20260912_9c5a8aed60e7_clave_de_idempotencia_en_reservas.py`, `backend/app/api/v1/bookings.py`, `backend/app/main.py`, `backend/app/models/booking.py`, `backend/app/schemas/bookings.py`, `backend/app/schemas/quotes.py`, `backend/app/services/bookings.py`, `backend/app/services/pricing.py`, `backend/tests/conftest.py`, `backend/tests/test_api_public.py`, `backend/tests/test_bookings.py`, `backend/pyproject.toml`, `backend/uv.lock`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **90 passed** (7 nuevos): redondo con tramos, vuelo e ítems que suman el total; misma `Idempotency-Key` dos veces → una sola reserva y respuesta idéntica; mismo email con otras mayúsculas → un cliente, teléfono completado y nombre intacto; one way de salida; actividad con park fee fuera del total; **F2.8:** subir todas las tarifas no cambia los ítems; montos del cliente o traslado local → 422 y ninguna reserva.
- `ruff`, `mypy`, `alembic check` (con la base local en head), `pip-audit` y `tsc` → sin errores.

**Decisiones a revisar**
- `promotions.used_count` se incrementará al pagar (F4), no al crear, para que reservas abandonadas no gasten usos.
- Una `Idempotency-Key` repetida con otro cuerpo devuelve la reserva original (la web genera una clave por checkout).

**Pendiente:** F3.2 (máquina de estados), F3.3 (fecha futura, formato de vuelo, horarios), F3.5 (token de gestión en la respuesta).

## 2026-09-12 — F2.4, F2.5 y F2.7: API pública de cotización y catálogo

**Qué se hizo**
- `app/api/deps.py`:
  - `get_company`: resuelve la empresa por `DEFAULT_COMPANY_SLUG` y fija `session.info["company_id"]`; si no existe → 503.
  - `cached_json`: respuesta con `ETag` (blake2b del cuerpo) y `Cache-Control: public, max-age=60`; con `If-None-Match` igual → 304 sin cuerpo.
- `app/core/rate_limit.py`: ventana fija por ruta e IP en `app.state` (quotes 60/min, catálogo 120/min) con `Retry-After`. En memoria hasta F13.3.
- `POST /api/v1/quotes`: unión discriminada por `type` (`transfer` | `activity`). La fecha "hoy" de las promociones sale de la zona horaria de la empresa (se agregó `tzdata`). `QuoteError` → 422 con `{"detail": {"code", "message"}}`.
- `GET /api/v1/catalog/zones` (con precio "desde"), `/hotels?q=`, `/hotels/{slug}` (tarifas de su zona), `/vehicles`, `/extras`, `/activities`, `/packages`. Textos en ambos idiomas para que la respuesta sea cacheable.
- Búsqueda de hoteles (`app/services/catalog.py`): nombre + alias sin acentos ni mayúsculas; primero los que empiezan con lo escrito, luego `word_similarity` de pg_trgm. Comodines escapados y máximo 10.
- Cliente tipado regenerado (`packages/api-client/src/schema.d.ts`).

**Archivos:** `backend/app/api/deps.py`, `backend/app/api/v1/catalog.py`, `backend/app/api/v1/quotes.py`, `backend/app/core/config.py`, `backend/app/core/rate_limit.py`, `backend/app/main.py`, `backend/app/schemas/catalog.py`, `backend/app/schemas/quotes.py`, `backend/app/services/catalog.py`, `backend/tests/test_api_public.py`, `backend/tests/test_hotel_search.py`, `backend/.env.example`, `backend/pyproject.toml`, `backend/uv.lock`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **83 passed** (20 nuevos):
  - Búsqueda: "riu pal", "Zadún", "one only", "golf & spa" y "BREATHLESS" encuentran su hotel; nunca devuelve hoteles de otra empresa; "r" y "%%" → vacío.
  - API: cotización de traslado y de actividades; payload inválido → 422 con el campo; hotel inexistente → `hotel_not_found`; zonas con precio "desde" y segunda llamada con ETag → 304; listas del catálogo; página de hotel y 404; la petición 61 a quotes → 429; empresa no configurada → 503.
- `ruff`, `mypy app scripts`, `alembic check`, `pip-audit` y `tsc` del cliente → sin errores.

**Nota de rendimiento:** la búsqueda recorre los ~230 hoteles de la empresa (milisegundos). Si el catálogo crece a miles, agregar una columna normalizada con índice GIN trigram.

**Pendiente:** F2.8 (se prueba al crear reservas en F3.1) y F2.9 (revisión de Marlon del ADR-002).

## 2026-09-12 — F2.1, F2.2, F2.3 y F2.6: motor único de precios

**Qué se hizo**
- `app/schemas/quotes.py`:
  - `TransferQuoteRequest`: estricto (campos desconocidos → 422), 1 tramo para ida y 2 para redondo, regreso no antes de la llegada, extras sin repetir.
  - `ActivityQuoteRequest`, `QuoteLine` y `Quote`.
- `app/services/pricing.py`, que es el único lugar donde se calcula un precio (D8):
  - **Vehículo automático** por pasajeros; subir de clase sí, bajar no; más de 14 → `too_many_passengers`.
  - **Tarifa base** de zona × vehículo × viaje × servicio; si no existe → `rate_unavailable`.
  - **Extras** validados: activos, no incluidos ni automáticos, cantidad ≤ `max_qty`. Precio × cantidad, una vez por reserva.
  - **Recargo nocturno automático** con la ventana de `company_settings`, que puede cruzar la medianoche (`in_night_window`).
  - **Promociones:** automáticas o por código; ventanas de viaje y compra; usos disponibles. Solo la de mayor descuento, con alcance a la base o al subtotal.
  - **Actividades:** paquete × invitados, con park fee en sitio y depósito informados aparte.
- `docs/decisions/ADR-002-precios.md`: todas las reglas con ejemplos numéricos. **Pendiente de revisión de Marlon (F2.9).**

**Archivos:** `backend/app/schemas/__init__.py`, `backend/app/schemas/quotes.py`, `backend/app/services/pricing.py`, `backend/tests/test_pricing.py`, `docs/decisions/ADR-002-precios.md`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **63 passed**. 19 tests nuevos de precios, todos sobre el catálogo real sembrado en la sesión:
  - Tarifa base de las 6 zonas × Suburban/Sprinter × ida/redondo = catálogo.
  - 1 y 5 pasajeros → Suburban; 6 y 14 → Sprinter; 15 → error; Sprinter para 2 sí; Suburban para 7 no.
  - Silla de bebé ×2 = $30. Rechazados: ×3 (máximo 2), recargo nocturno pedido a mano, kit incluido y código inexistente.
  - Recargo nocturno: 23:00 y 04:59 cobran; 05:00, 22:59 y sin hora no cobran.
  - 15 sep con silla de bebé → subtotal $125, descuento $11, total $114. 15 oct → sin descuento.
  - Código `vip20` (fijo $20) gana al 10% automático, con una sola línea de descuento; código inválido → `invalid_promo_code`.
  - Crazy Combo, 2 personas → $250, park fee $50 en sitio; conteo, repetidas o actividad inexistente → error.
  - Validación: redondo con 1 tramo, regreso antes de la llegada o campo extra (`price_cents`) → `ValidationError`.
- `ruff check`, `ruff format` y `mypy app scripts` → 0 errores. `alembic check` sin cambios de esquema.

**Pendiente:** F2.4 (`POST /quotes`), F2.5 (búsqueda de hoteles), F2.7 (caché del catálogo), F2.8 (se prueba al crear reservas en F3.1) y F2.9 (revisión de Marlon).

## 2026-09-12 — F1.11 Códigos de reserva y F1.12 diagnóstico de la base (F1 completa)

**Qué se hizo**
- **F1.11:**
  - `app/models/sequences.py` con `BookingCodeCounter` (PK empresa + año, `last_value >= 1`, cascada desde la empresa) y migración `523ec6ce4943`.
  - `app/services/booking_codes.py` con `next_booking_code(session, company_id, year)` → `CTC-2026-000001`.
  - Un solo `INSERT … ON CONFLICT (company_id, year) DO UPDATE SET last_value = last_value + 1 RETURNING last_value`. Postgres bloquea la fila del contador hasta el commit, así que dos reservas simultáneas nunca reciben el mismo código. ClassVIP usaba `COUNT(*)` y chocaba (E7).
- **F1.12:** `scripts/check_db.py` reporta:
  - Latencia de `SELECT 1`.
  - Versión de Postgres.
  - Migración actual y head de Alembic, y si están al día.
  - Conteos de `companies`, `hotels`, `rates`, `bookings`, `payments` y `email_outbox`.

  Sale con código 1 si no conecta (sin mostrar el detalle de la URL) o si faltan migraciones.
- Ajuste de tipos: `insert()` recibe el modelo y sus columnas ORM, no `__table__`. Mismo patrón que en el seed; mypy estricto limpio.

**Archivos:** `backend/app/models/sequences.py`, `backend/app/models/__init__.py`, `backend/app/services/__init__.py`, `backend/app/services/booking_codes.py`, `backend/alembic/versions/20260912_523ec6ce4943_contador_de_codigos_de_reserva.py`, `backend/scripts/check_db.py`, `backend/tests/test_booking_codes.py`, `backend/tests/test_check_db.py`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **44 passed**. Tests nuevos:
  - Códigos consecutivos que reinician en 2027.
  - **50 reservas concurrentes** en transacciones y conexiones separadas: códigos `CTC-2026-000001` a `000050`, sin repetir.
  - `check_db` al día contra la base de tests.
  - `check_db` con head distinto → `up_to_date: False` y sin conteos.
- **Caso real:** la verificación anterior se detuvo en mypy antes de migrar `ctc`. Al correr `check_db` reportó `migration a6a95d459beb` contra head `523ec6ce4943`, `up_to_date: False`, y salió con código 1 con la instrucción de `alembic upgrade head`. Después de migrar: `up_to_date: True`, filas `companies 1, hotels 226, rates 24, bookings 0, payments 0, email_outbox 0`, código 0.
- `alembic check` → "No new upgrade operations detected".
- `ruff check`, `ruff format` y `mypy app scripts` → 0 errores.
- CI del commit anterior `2ed109a` (run `34728586891`) → los 3 jobs en success.

**F1 queda completa (12/12).** Pendiente de Marlon: aprobar la matriz de tarifas (D-P1) y confirmar la zona de Los Cabos Golf Resort (D-P13). Siguiente: F2, motor de precios.

## 2026-09-12 — F1.10 Creación del owner

**Qué se hizo**
- Dependencia `pwdlib[argon2]` 0.3.1.
- `app/core/security.py`: `hash_password` (Argon2id; rechaza contraseñas de menos de 12 caracteres) y `verify_password`. Es la base del login de F6.1.
- `scripts/ensure_owner.py`: crea el usuario `owner` de la empresa con `OWNER_EMAIL` y `OWNER_PASSWORD` del entorno.
  - Nunca inventa ni imprime la contraseña.
  - El email se guarda normalizado (sin espacios y en minúsculas).
  - Si ya existe un admin con ese email, no cambia nada. Es la regla de Marlon heredada de ClassVIP: no crear admins ni contraseñas por cuenta propia.
  - Si la empresa no existe, falla indicando que primero hay que correr el seed.

**Archivos:** `backend/app/core/security.py`, `backend/scripts/ensure_owner.py`, `backend/tests/test_ensure_owner.py`, `backend/pyproject.toml`, `backend/uv.lock`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **40 passed**. Tests nuevos:
  - El owner se crea una vez; la segunda llamada con el mismo email en otra capitalización devuelve `False`. Hay un solo admin, con rol owner, email en minúsculas, hash que empieza con `$argon2id$` y que `verify_password` valida.
  - Contraseña corta → `ValueError`.
  - Empresa inexistente → `LookupError` que menciona `seed_catalog`.
- `uv run pip-audit` → "No known vulnerabilities found".
- `ruff check`, `ruff format` y `mypy app scripts` → 0 errores.

**Pendiente:** F1.11 (secuencia de códigos de reserva) y F1.12 (`check_db`).

## 2026-09-12 — F1.9 Seed del catálogo y depuración de hoteles

**Qué se hizo**
- `backend/scripts/data/catalog.json` (versionado), para que el seed no dependa de la carpeta de ClassVIP y funcione igual en CI. Contiene:
  - Empresa.
  - 6 zonas bilingües con tiempos desde SJD.
  - 2 clases de vehículo: Suburban de 1 a 5 pasajeros y Sprinter de 6 a 14.
  - 24 tarifas en centavos.
  - 15 extras.
  - 5 actividades y 2 combos.
  - La promoción automática "September 10% off".
  - `meta.status = pending_approval`.
- `backend/scripts/seed_catalog.py`:
  - Upsert con `INSERT … ON CONFLICT DO UPDATE` por la llave única de cada tabla, así que es idempotente. Devuelve los ids para ligar hoteles y tarifas a zonas y vehículos.
  - Las promociones sin código se reconocen por su nombre.
  - `--dry-run` imprime la matriz de tarifas en español sin tocar la base; `sys.stdout` va en UTF-8 para que los acentos salgan bien en la consola de Windows.
- **Depuración de hoteles de ClassVIP** (reporte agrupando por nombre normalizado):
  - 252 hoteles activos que en realidad eran **226**.
  - 23 eran el mismo hotel escrito distinto ("&" / "and", con o sin "Resort and Spa"). El nombre más completo quedó como principal y los demás como `aliases` para la búsqueda (17 hoteles con alias). Se quitó un alias que solo cambiaba mayúsculas ("ME Cabo" = "Me Cabo").
  - **15 estaban en dos o más zonas, con precios distintos.** Se asignó la zona por ubicación real:
    - Hard Rock, Nobu y Pueblo Bonito Pacifica → Lado Pacífico.
    - Breathless, Riu Palace, Marina Fiesta y Cabo Vista → Cabo San Lucas.
    - One&Only Palmilla, Grand Velas, Hilton y Marbella Suites → Corredor Turístico.
    - JW Marriott, Secrets y El Ganzo → Puerto Los Cabos.
    - Queda registrado en `meta.hotel_zone_decisions`.
  - **Los Cabos Golf Resort queda por confirmar** (D-P13, agregado al checklist del cliente).
- **Extras:** `LATE_NIGHT` y `EARLY_MORNING` de ClassVIP se unieron en un solo `NIGHT_SURCHARGE` de $20, 11 PM – 5 AM (D-P12), y se agregó el kit básico incluido ("Cold beer and water").
- CI: `mypy app scripts` (antes solo revisaba `app`).

**Archivos:** `backend/scripts/__init__.py`, `backend/scripts/seed_catalog.py`, `backend/scripts/data/catalog.json`, `backend/tests/test_seed_catalog.py`, `.github/workflows/ci.yml`, `docs/content/checklist-cliente.md`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **37 passed**. Tests nuevos:
  - Matriz sin huecos: cada zona × vehículo × tipo de viaje, con precio > 0.
  - Cada hotel aparece una sola vez (nombre y aliases sin repetir) y en una zona existente.
  - Seed idempotente: dos corridas dan los mismos conteos en la base.
- `uv run python -m scripts.seed_catalog` dos veces en `ctc` → ambas `hotels 226, rates 24, zones 6, extras 15, activities 5, activity_packages 2, promotions 1`. En Postgres: `hotels=226 rates=24 zones=6 extras=15 promos=1 companies=1`.
- Zonas corregidas en la base: Hard Rock → `pacific-side`, Marina Fiesta → `cabo-san-lucas`, One and Only Palmilla → `tourist-corridor`.
- `ruff check`, `ruff format` y `mypy app scripts` → 0 errores.
- CI del commit anterior `e08d0cd` (run `34728171656`) → los 3 jobs en success.

**Matriz de tarifas por aprobar** (`--dry-run`):

| Zona | Suburban ida / redondo | Sprinter ida / redondo |
|---|---|---|
| San José del Cabo | $90 / $162 | $130 / $234 |
| Puerto Los Cabos | $95 / $171 | $135 / $243 |
| Corredor Turístico | $100 / $180 | $145 / $261 |
| Cabo San Lucas | $110 / $198 | $155 / $279 |
| Lado Pacífico | $130 / $234 | $175 / $315 |
| East Cape y Todos Santos | $150 / $270 | $205 / $369 |

**Pendiente:** F1.10 (owner), F1.11 (secuencia de códigos), F1.12 (`check_db`); aprobación de tarifas (D-P1) y zona de Los Cabos Golf Resort (D-P13).

## 2026-09-12 — F1.8 Operación y comunicación

**Qué se hizo**
- `app/models/operations.py`:
  - `Driver`
  - `Vehicle`: placa única por empresa, capacidad ≥ 1, `RESTRICT` sobre la clase de vehículo.
  - `BookingAssignment`: una por tramo; exige chofer o vehículo, que no se pueden borrar mientras estén asignados; índice por chofer para detectar choques de horario en F6.7.
  - `AdminTask`: tareas compartidas por empresa (en ClassVIP vivían solo en localStorage), con índice por estado y fecha.
  - `AuditLog`: actor, acción, entidad y antes/después en JSONB, con índices por entidad y por fecha para el visor.
- `app/models/communication.py`:
  - `EmailOutbox`: cola del worker (D7) con reintentos. El índice parcial `status = 'pending'` deja que el worker tome solo lo pendiente, sin recorrer lo ya enviado.
  - `AiConversation` y `AiMessage`:
    - El visitante anónimo se identifica solo por el hash de su token.
    - El costo se guarda en `cost_micro_usd` (entero, sin errores de punto flotante).
    - Los mensajes se borran con la conversación.
  - `ContactMessage`: bandeja con índice por estado y fecha.
  - `Review`: `rating BETWEEN 1 AND 5` y enlace de origen.
- Migración `a6a95d459beb` revisada: 10 tablas, nombres de constraints claros, `ondelete` correcto y downgrade con las 19 operaciones.
- **Con esto el modelo de datos de WORKPLAN §6 está completo.**

**Archivos:** `backend/app/models/operations.py`, `backend/app/models/communication.py`, `backend/app/models/__init__.py`, `backend/alembic/versions/20260912_a6a95d459beb_operacion_y_comunicacion.py`, `backend/tests/test_models_operations.py`, `backend/tests/test_models_communication.py`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **34 passed**. Tests nuevos:
  - Dos asignaciones para el mismo tramo → `uq_booking_assignments_leg_id`.
  - Asignación sin chofer ni vehículo → `ck_booking_assignments_driver_or_vehicle`.
  - Placa repetida → `uq_vehicles_company_id_plate`.
  - Un correo recién encolado queda `pending`, con 0 intentos y `next_attempt_at` definido.
  - Borrar una conversación borra sus mensajes.
  - Calificación 6 → `ck_reviews_rating_range`.
- `alembic upgrade head` en `ctc` y luego `alembic check` → "No new upgrade operations detected".
- `ruff check`, `ruff format` y `mypy app` → 0 errores.
- CI del commit anterior `825bcb5` (run `34727966391`) → los 3 jobs en success.

**Pendiente:** F1.9 (seed del catálogo, con la matriz de tarifas por aprobar), F1.10 (owner), F1.11 (secuencia de códigos) y F1.12 (`check_db`).

## 2026-09-12 — F1.7 Pagos, eventos de Stripe y cuentas por cobrar

**Qué se hizo**
- `app/models/finance.py` con enums `PaymentProvider`, `PaymentStatus`, `AccountStatus`, `ChargeStatus` y `AccountPaymentMethod`, y estos modelos:
  - **`Payment`:**
    - `ck_payments_amounts`: monto > 0 y reembolso entre 0 y el monto.
    - `stripe_payment_intent_id` y `stripe_checkout_session_id` únicos, para que un intent o checkout nunca genere dos pagos (E9).
    - `RESTRICT` sobre `bookings`.
  - **`StripeEvent`:** la PK es el id del evento de Stripe, así un webhook repetido choca y no se procesa dos veces. Sin `company_id`, porque el webhook llega antes de saber de qué empresa es.
  - **`ClientAccount`, `AccountCharge` y `AccountPayment`:** crédito de clientes con montos siempre > 0. **El saldo no se guarda:** se calcula de cargos y abonos para que nunca se desincronice. §6 del WORKPLAN se corrigió, porque decía `balance_cents`.
- **Ajuste en `Booking`:** `passive_deletes=True` en `legs` e `items`. Sin esto, borrar una reserva hacía que el ORM intentara cargar los hijos, y eso chocaba con `raise_on_sql` antes de llegar a la base. Ahora Postgres aplica `ON DELETE CASCADE` sin cargar nada, que además es más rápido.
- Migración `56ed3ca7c373` revisada a mano: nombres de constraints claros y `ondelete` correcto. `passive_deletes` no cambia el esquema.

**Archivos:** `backend/app/models/finance.py`, `backend/app/models/booking.py`, `backend/app/models/__init__.py`, `backend/alembic/versions/20260912_56ed3ca7c373_pagos_y_finanzas.py`, `backend/tests/test_models_finance.py`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **28 passed**. Tests nuevos:
  - Mismo intent dos veces → `uq_payments_stripe_payment_intent_id`.
  - Reembolso mayor al monto → `ck_payments_amounts`.
  - Evento de Stripe repetido → `pk_stripe_events`.
  - Cargo en 0 → `ck_account_charges_amount_positive`.
  - Borrar una reserva con pagos → `fk_payments_booking_id_bookings`.
- `alembic upgrade head` en `ctc` y luego `alembic check` → "No new upgrade operations detected".
- `ruff check`, `ruff format` y `mypy app` → 0 errores.
- CI del commit anterior `283543e` (run `34727831270`) → los 3 jobs en success.

**Pendiente:** F1.8 (operación y comunicación, más `booking_assignments`), F1.9 (seed del catálogo), F1.10 (owner), F1.11 (secuencia de códigos) y F1.12 (`check_db`).

## 2026-09-12 — F1.5 Reservas, tramos e ítems

**Qué se hizo**
- `app/models/booking.py` con enums `BookingStatus`, `BookingSource`, `BookingType`, `LegType`, `LegStatus` e `ItemType`, y tres modelos (todos con `TenantMixin`):
  - **`Booking`:** código único por empresa, estado, origen, cliente, idioma, moneda, promoción, admin creador, UTM, cancelación y borrado lógico.
  - **`BookingLeg`:** tramo en tabla propia (D11) con fecha y hora, pickup, vuelo, origen y destino, hotel, pasajeros y clase de vehículo.
  - **`BookingItem`:** precio congelado por línea, opcionalmente ligado a un tramo.
- Reglas en la base:
  - `ck_bookings_totals`: `total = subtotal − descuento + impuesto`, sin negativos.
  - `ck_booking_items_amounts`: `total = cantidad × unitario`, y solo el ítem `discount` puede ser negativo.
  - `ck_booking_legs_pax`: al menos 1 adulto.
  - Código único por empresa.
- Índices: `ix_bookings_company_status_created` (listado del admin con todos los estados, para prevenir E1) y `ix_booking_legs_company_service_date` (despacho por día).
- Relaciones `legs` e `items` con `lazy="raise_on_sql"` y `cascade="all, delete-orphan"`: acceder a tramos o ítems sin `selectinload` lanza error en lugar de disparar consultas N+1 silenciosas.
- `booking_assignments` pasa a F1.8, junto con `drivers` y `vehicles`.
- La fixture `catalog` (empresa en sesión, zona y Suburban) se movió a `conftest.py` y la comparten los tests de catálogo y reservas.
- Migración `0b3217285efc` revisada a mano antes de aplicarla:
  - Nombres de constraints claros y `ondelete` correcto por FK.
  - Sin índices en `hotel_id`, `vehicle_class_id` ni `leg_id`, a propósito: solo sirven para borrar hoteles, vehículos o tramos, que en la práctica se desactivan en lugar de borrarse. Se agregan cuando una consulta real los necesite.

**Archivos:** `backend/app/models/booking.py`, `backend/app/models/__init__.py`, `backend/alembic/versions/20260912_0b3217285efc_reservas.py`, `backend/tests/test_models_booking.py`, `backend/tests/conftest.py`, `backend/tests/test_models_catalog.py`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **23 passed**. Tests nuevos:
  - Reserva con llegada y salida, transfer, champagne y descuento de septiembre: se relee completa y los ítems suman el total (235.00 USD).
  - Totales que no cuadran → `ck_bookings_totals`.
  - Acceso a `legs` sin cargar → `InvalidRequestError`.
- `alembic upgrade head` en `ctc` y luego `alembic check` → "No new upgrade operations detected".
- `ruff check`, `ruff format` y `mypy app` → 0 errores.
- CI del commit anterior `658c3a1` (run `34727673529`) → los 3 jobs en success.

**Pendiente:** F1.7 (pagos y finanzas), F1.8 (operación y comunicación, más `booking_assignments`) y F1.9 a F1.12.

## 2026-09-12 — F1.6 Catálogo y clientes

**Qué se hizo**
- `app/models/catalog.py` con enums (`TripType`, `ServiceScope`, `PricingMode`, `ExtraAutoRule`, `DiscountType`, `PromotionScope`) y modelos `Zone`, `Hotel`, `VehicleClass`, `Rate`, `Extra`, `Activity`, `ActivityPackage` y `Promotion`. Todos usan `TenantMixin`, así que quedan aislados por empresa (F1.2).
- `app/models/customer.py`: `Customer` con email único por empresa sin importar mayúsculas. Se hizo antes que F1.5 porque las reservas lo referencian.
- Reglas en la base:
  - Una tarifa por combinación (`uq_rates_zone_vehicle_trip_scope`).
  - `price_cents >= 0`, rango de pasajeros válido y porcentaje ≤ 100.
  - Código de promoción único sin importar mayúsculas; varias promociones sin código están permitidas porque son automáticas por fechas.
  - Índice GIN trigram en el nombre del hotel, para la búsqueda de F2.5.
- Solo campos que usa el motor de precios (regla de código mínimo): sin dirección, coordenadas ni imágenes hasta F9.

**Encontrado al revisar la migración antes de aplicarla**
1. Faltaba `CREATE EXTENSION pg_trgm`, porque autogenerate no crea extensiones. Se agregó a mano al inicio de `upgrade()`.
2. La naming convention usaba solo la primera columna, así que todos los unique compuestos salían como `uq_<tabla>_company_id`: nombres engañosos y con riesgo de choque. Se cambió a `column_0_N_name` (todas las columnas) y `rates` recibió un nombre explícito corto para no pasar el límite de 63 caracteres de Postgres. Los nombres de la migración anterior no cambian porque son de una sola columna.

**Archivos:** `backend/app/models/catalog.py`, `backend/app/models/customer.py`, `backend/app/models/__init__.py`, `backend/app/db.py`, `backend/alembic/versions/20260912_4b96b66d17b0_catalogo_y_clientes.py`, `backend/tests/test_models_catalog.py`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **20 passed**. Tests nuevos: tarifa duplicada, precio negativo, slug de hotel repetido, código de promo repetido sin importar mayúsculas (sin código sí se permite), email de cliente repetido y `pg_trgm` instalada.
- `alembic upgrade head` en `ctc` y luego `alembic check` → "No new upgrade operations detected".
- `ruff check`, `ruff format --check` y `mypy app` → 0 errores.
- CI del commit anterior `8d7994c` (run `34727447942`) → los 3 jobs en success.

**Pendiente:** F1.5 (reservas), F1.7 (pagos y finanzas), F1.8 (operación y comunicación) y F1.9 a F1.12.

## 2026-09-12 — F1.2 Aislamiento por empresa en el ORM

**Qué se hizo**
- `app/tenancy.py` con `TenantMixin` (columna `company_id` con FK a `companies` y `ondelete=CASCADE`) y dos eventos de sesión:
  - **`do_orm_execute`:** si `session.info["company_id"]` está definido, agrega a todo SELECT el filtro `with_loader_criteria(TenantMixin, company_id == …)`, incluso con aliases. El aislamiento no depende de que cada servicio recuerde filtrar.
  - **`before_flush`:** completa el `company_id` faltante en filas nuevas y lanza `CrossTenantWriteError` si una fila nueva o modificada pertenece a otra empresa.
- `AdminUser` usa `TenantMixin`. La columna es idéntica, así que la migración no cambia.
- La dependencia que fija la empresa del request (`get_company`) se agrega con el primer endpoint que la usa (F2.4 web, F6.1 admin), para no dejar código sin uso.

**Archivos:** `backend/app/tenancy.py`, `backend/app/models/admin.py`, `backend/tests/test_tenancy.py`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **14 passed**. Tests nuevos:
  - Con la sesión en la empresa B, `select(AdminUser)` y `count()` solo ven su admin.
  - El flush completa el `company_id` y rechaza un admin de otra empresa.
- `uv run alembic check` → "No new upgrade operations detected" (el esquema no cambió).
- `ruff check`, `ruff format` y `mypy app` → 0 errores.
- CI del commit anterior `5fad5d1` (run `34727349395`) → backend, api-client y secrets en success, incluido el nuevo paso `alembic upgrade head && alembic check`.

**Pendiente:** F1.5 a F1.12.

## 2026-09-12 — F1.1, F1.3 y F1.4: base de datos, Alembic y primeros modelos

**Qué se hizo**
- **F1.1 `app/db.py`:**
  - `normalize_url` (fuerza asyncpg y quita `pgbouncer`, lección de ClassVIP) y `engine_from_url`: pool 5+5, `pre_ping`, `recycle 300`, SSL fuera de localhost, y en el puerto 6543 NullPool con nombres únicos de prepared statements.
  - `get_session` sin commit implícito.
  - `Base` con naming convention, fechas con zona horaria, JSONB, y enums como texto con CHECK para que los downgrades no dejen tipos huérfanos.
  - `IdMixin` y `TimestampMixin`.
- **F1.3 Alembic:** `alembic.ini` mínimo, `env.py` async por `DATABASE_URL_DIRECT` (o `DATABASE_URL`) y plantilla tipada. En CI, `alembic upgrade head && alembic check`.
- **F1.4 Modelos:** `companies`, `company_settings` (contacto, oficinas, políticas y horario del recargo nocturno configurables, textos bilingües), `admin_users` (roles owner, manager, dispatcher, finance y viewer; email único por empresa sin importar mayúsculas; bloqueo por intentos; TOTP) y `sessions` (hashes de token y CSRF, expiración y revocación).
- **Tests:** la fixture de sesión hace `downgrade base` y `upgrade head` en cada corrida; cada test corre en una transacción que se revierte.

**Bug encontrado y corregido antes del commit:** el índice único se generó como `lower('email')` (el texto literal, no la columna), porque el modelo usaba `func.lower("email")`. Con eso cada empresa solo habría podido tener **un** admin. Se cambió a `text("lower(email)")`, se regeneró la migración y se agregó al test el caso de dos admins distintos en la misma empresa.

**Archivos:** `backend/app/db.py`, `backend/app/main.py`, `backend/app/core/config.py`, `backend/app/models/*`, `backend/alembic.ini`, `backend/alembic/*`, `backend/tests/*`, `backend/pyproject.toml`, `backend/.env.example`, `.github/workflows/ci.yml`

**Verificación**
- `uv run pytest` → 12 tests en verde.
- `pg_indexes` → `CREATE UNIQUE INDEX uq_admin_users_company_email ON public.admin_users USING btree (company_id, lower((email)::text))`.
- `alembic upgrade head` en `ctc` y luego `alembic check` → "No new upgrade operations detected".
- `ruff check`, `ruff format --check` y `mypy app` → 0 errores.

**Pendiente:** F1.2 (scope por empresa en consultas) y F1.5 a F1.12.

## 2026-09-12 — Vista previa en Vercel + cierre de F0

**Qué se hizo**
- Marlon conectó el repo a Vercel y no se veía nada. **Causa:** la raíz del repo no tiene `index.html`; el prototipo vive en `site/`. Vercel respondía `X-Vercel-Error: NOT_FOUND`.
- `vercel.json`:
  - `outputDirectory: site` (sin build) y `cleanUrls`.
  - Headers `X-Robots-Tag: noindex, nofollow`: el prototipo aún tiene textos y fotos de All Ways y no debe indexarse.
  - `nosniff`, `X-Frame-Options: DENY` y `Referrer-Policy`.
  - Caché de 7 días para `images/`, `videos/` y `build/`.
- Arrival Guide: el video de All Ways (no versionado) se reemplazó por la imagen propia `sprinter-interior.jpg` (D-P6).
- F0.2 cerrada: Marlon borró la key de OpenRouter y esa key no se usa en este proyecto. **F0 queda 9/9.**

**Archivos:** `vercel.json`, `site/build.js`, `site/arrival-guide.html`, `WORKPLAN.md`

**Verificación**
- Commit `1c1471a`, auto-deploy de Vercel.
- `https://cabotransportationconcierge.vercel.app/` → 200 con `X-Robots-Tag: noindex, nofollow`.
- `arrival-guide`, `luxe.css`, `hero-suburban.jpg`, `videos/hero-promo-light.mp4` (6.4 MB) y `images/svg/logo-ctc.svg` → 200.
- Script de referencias: 77 archivos locales del home y 8 de Arrival Guide, todos versionados.

**Pendiente / riesgos:** es solo el prototipo estático. Muchos links del navbar siguen en `#` hasta F9, y el cotizador y el chat son simulados hasta F8 y F10.

## 2026-09-12 — F0.7 CI en GitHub

**Qué se hizo**
- Remoto `github.com/condecorporation-del/Cabotransportationconcierge` con deploy key `~/.ssh/deploy_cabo_concierge` (alias SSH `github-cabo`). Push de `main`.
- **Primera corrida** (run `34726625131`, commit `bf8a0ba`): backend ✅, api-client ✅, secrets ❌. `gitleaks/gitleaks-action@v2` salió con código 1 sin detalle legible sin autenticación; el escaneo local del historial (`gitleaks git .`, 8.30.1) estaba limpio.
- **Arreglo** (commit `b8d66dd`):
  - El job `secrets` ahora descarga gitleaks 8.30.1 (la misma versión que en local) y verifica su SHA-256 `551f6fc8…70eb` antes de correr `gitleaks git . --redact -v`.
  - Actions actualizadas a `checkout@v6`, `setup-node@v6` y `setup-uv@v7`. Esto quita los avisos de Node 20 deprecado.

**Archivos:** `.github/workflows/ci.yml`, `WORKPLAN.md`

**Verificación:** run `34726728816` → `completed success` en api-client, backend y secrets, sin anotaciones (consultado con la API pública de GitHub).

**Pendiente / riesgos:** F0.2, rotar la API key de OpenRouter (tarea de Marlon).

## 2026-09-12 — F0 Fundación

**Qué se hizo**
- **F0.1:** repo git (`main`) con `.gitignore` (secretos, media pesada, material de terceros) y `.gitattributes` (LF). Primer commit `6eb258f`.
- **F0.2:** la API key de OpenRouter salió del repo a `C:\Users\conde\.secrets\`, y `site/video/generate.mjs` ahora la lee de `OPENROUTER_API_KEY`.
- **F0.3:** estructura creada a medida que se usa (`backend/`, `packages/api-client/`, `docs/`, `.github/`). `web/` y `admin/` se crean en F7 y F11.
- **F0.4:** backend con uv y Python 3.12. `app/main.py` (lifespan con pool 5+5, `pre_ping`, `recycle`), `app/api/v1/health.py` (liveness y readiness con timeout de 2 s) y `app/openapi.py`.
- **F0.5:** Postgres 16.15 nativo (ADR-001) con bases `ctc` y `ctc_test`; fixture de pytest contra Postgres real; Mailpit v1.31.1.
- **F0.6:** `packages/api-client` genera `src/schema.d.ts` con openapi-typescript y expone un cliente tipado con openapi-fetch.
- **F0.7:** `.github/workflows/ci.yml`: backend (ruff, mypy, pytest con Postgres de servicio, pip-audit), cliente de API (gen, diff del contrato, tsc, npm audit) y gitleaks.
- **F0.8:** `core/config.py` fail-fast y `.env.example`.
- **F0.9:** `docs/content/checklist-cliente.md`.
- `AGENTS.md` §5.0 con los principios de código mínimo, performance, escalabilidad y seguridad pedidos por Marlon.

**Archivos:** `.gitignore`, `.gitattributes`, `README.md`, `backend/**`, `packages/api-client/**`, `.github/workflows/ci.yml`, `docs/decisions/ADR-001-entorno-local.md`, `docs/content/checklist-cliente.md`, `site/video/generate.mjs`, `WORKPLAN.md`, `AGENTS.md`.

**Verificación**
- `uv run ruff format --check . && uv run ruff check . && uv run mypy app` → "All checks passed!" y "no issues found in 8 source files".
- `uv run pytest -v` → **6 passed** (config fail-fast ×3, health, readiness contra Postgres real y 503 con la base inaccesible).
- `uv run pip-audit` → "No known vulnerabilities found". `npm install` → "found 0 vulnerabilities".
- `npm run gen && npm run check` → contrato generado y tsc sin errores. Prueba negativa: `api.GET("/api/health")` → error TS2345 (una ruta sin `/v1` no compila).
- `gitleaks dir .` → "no leaks found" (164 MB escaneados).
- `git check-ignore` confirma que se ignoran `backend/.env`, `site/video/gen/` y `site/original.html`.

**Pendiente / riesgos**
- **F0.2:** Marlon debe **rotar la API key de OpenRouter** (se compartió en el chat). Hasta entonces no se marca como terminada.
- **F0.7:** el CI no se ha ejecutado; falta el remoto de GitHub. Las versiones de las actions (`checkout@v4`, `setup-uv@v6`, `setup-node@v4`, `gitleaks-action@v2`) se confirman en la primera corrida.
- `uv`, `gitleaks` y `mailpit` quedaron en el PATH de usuario; las terminales abiertas antes de la instalación necesitan reiniciarse.

**Decisiones:** ADR-001 (Postgres nativo y Mailpit binario sin Docker; reglas `S` de ruff en lugar de bandit).
