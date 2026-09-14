# Bitácora — Cabo Transportation Concierge

Una entrada por sesión o tarea, la más reciente arriba (formato en `AGENTS.md` §10).

## 2026-09-13 — F6.7: despacho (tablero del día, asignar chofer y vehículo)

Con reservas ya completas (F6.4-F6.6), seguí con despacho porque desbloquea F5.9 (aviso al chofer) y es el último bloque de reservas antes de flota/cuentas (F6.8). Los modelos (`booking_assignments`, `drivers`, `vehicles`) ya existían desde F1.8, incluido el índice por chofer que F1.8 dejó puesto "para detectar choques de horario (F6.7)" — aquí por fin se usa.

**Decisión: ventana fija de ±2 h, no la duración real del viaje.** El criterio de verificación pide que asignar el mismo chofer a dos tramos solapados avise el conflicto, pero no dice cómo medir el solape. Calcularlo bien (tiempo de manejo por zona + regreso a base + tráfico) es trabajo real que no tiene sentido meter aquí a medias; `zones.drive_minutes_min/max` ya existe para eso, pero combinarlo con el resto queda para cuando el despacho necesite ser más preciso. Por ahora, dos tramos del mismo chofer cuyo pickup cae a menos de 2 horas uno de otro son un conflicto (`driver_conflict`, 409); más separados que eso, no. Es una simplificación a propósito, documentada en el código y aquí, no un descuido.

**`app/services/dispatch.py`** (nuevo): `dispatch_board(date)` arma el tablero con dos consultas (tramos del día que no están cancelados ni borrados, más sus asignaciones con el nombre del chofer y la placa del vehículo ya resueltos) y las junta en memoria — más simple que un `outerjoin` con duplicados por unidad. `assign()` valida que la unidad exista (`1..vehicle_count`, para los tramos con varias unidades de F2.11) y el choque de horario antes de crear o actualizar la fila de `booking_assignments` (unique por `leg_id` + `unit_index`, así reasignar es un upsert en la práctica). `unassign()` la borra.

**Archivos:** `backend/app/services/dispatch.py` (nuevo), `backend/app/schemas/dispatch.py` (nuevo), `backend/app/api/v1/admin/dispatch.py` (nuevo), `backend/app/api/v1/admin/deps.py` (`CAN_EDIT` se movió aquí, compartido ahora por `bookings.py` y `dispatch.py`), `backend/app/api/v1/admin/bookings.py`, `backend/app/main.py`, `backend/tests/test_admin_dispatch.py` (nuevo), `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **255 passed** (9 nuevos): el tablero muestra un tramo sin asignar; asignar chofer y vehículo se refleja con su nombre y placa; reasignar reemplaza al chofer anterior en vez de duplicar la fila; quitar la asignación la borra; una unidad fuera de rango es 422 `invalid_unit`; dos tramos con el mismo chofer a menos de 2 h son 409 `driver_conflict`, a más de 2 h se permiten los dos; una reserva cancelada no aparece en el tablero; sin el header CSRF, 403.
- `uv run ruff format --check . && uv run ruff check .` → sin errores. `uv run mypy app scripts` → sin errores.
- `uv run alembic check` (sin migración: los modelos ya existían desde F1.8) y `uv run pip-audit` → sin diferencias ni vulnerabilidades.
- `npm run gen && npm run check` en `packages/api-client` → contrato regenerado, `tsc` sin errores.

**Pendiente:** F6.8 (flota CRUD y cuentas por cobrar completas) es lo siguiente; hoy no hay forma de dar de alta un chofer o vehículo desde el admin, solo se prueban con filas creadas a mano.

## 2026-09-13 — F6.6: reserva manual del admin (none, cash, stripe, account)

Seguí con F6.6 porque completa el ciclo de vida de una reserva en el admin antes de pasar a despacho (F6.7): hasta ahora solo se podía actuar sobre una reserva que ya existía (F6.5); esta es la que el admin arma desde cero cuando el cliente reserva por teléfono o WhatsApp.

**Un solo motor de precios, de verdad (D8):** en vez de reimplementar la lógica de tramos y cotización, `create_manual_booking()` (nuevo, `services/bookings.py`) llama a los mismos `quote_transfer()` y `_transfer_legs()` que ya usaba `create_booking()` de la web. `_transfer_legs()` estaba tipado para recibir justo `TransferBookingRequest`; se amplió a `TransferQuoteRequest` (todo lo que en realidad usa) porque la nueva reserva del admin no lleva los campos de `_BookingFields` (términos, atribución) que sí exige el flujo público.

**Cómo se decide el estado (§8.2):** el mapa es literal y no pasa por el depósito de efectivo de la web — `none` → `OFFLINE_HOLD` (borrador), `cash` → `CONFIRMED` directo, `stripe` → `PENDING_PAYMENT` (a la espera de un link real, que es F4.6 y todavía no existe), `account` → `CONFIRMED` con un `AccountCharge` contra la cuenta del cliente (el modelo de F1.7 ya tenía todo lo necesario). A propósito no reusa la regla "depósito en efectivo espera pago" de la reserva pública: aquí el admin ya negoció los términos con el cliente por teléfono, así que "cash" siempre confirma.

**`payment` dejó de ser solo `card`/`cash`:** se amplió el campo único de `TransferQuoteRequest` (motor compartido entre cotización pública, reserva pública y alta manual) a `card | cash | stripe | none | account`, y `TransferBookingRequest` (la reserva pública) ganó su propio validador que rechaza cualquier valor que no sea `card` o `cash` — un cliente no puede pedir que se le facture a una cuenta ajena. `pricing.py` trata `stripe` igual que `card` para el IVA (`taxed = request.payment in ("card", "stripe")`): es un cobro por tarjeta, solo que con un link en vez de pagarlo al instante.

**Archivos:** `backend/app/services/pricing.py`, `backend/app/services/bookings.py`, `backend/app/schemas/quotes.py`, `backend/app/schemas/bookings.py`, `backend/app/schemas/admin_bookings.py`, `backend/app/api/v1/admin/bookings.py`, `backend/tests/test_admin_manual_bookings.py` (nuevo), `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **246 passed** (8 nuevos): `none` deja `OFFLINE_HOLD`; `cash` confirma directo; `stripe` queda `PENDING_PAYMENT` y paga el mismo IVA que una reserva idéntica en `card`; `account` confirma y deja un `AccountCharge` por el total exacto; sin `account_id` es 422; una cuenta de otro cliente es 422 `account_not_found`; el endpoint público sigue rechazando `stripe`/`none`/`account`; sin el header CSRF, 403.
- `uv run ruff format --check . && uv run ruff check .` → sin errores. `uv run mypy app scripts` → sin errores.
- `uv run alembic check` (sin migración: todo el esquema ya existía) y `uv run pip-audit` → sin diferencias ni vulnerabilidades.
- `npm run gen && npm run check` en `packages/api-client` → contrato regenerado, `tsc` sin errores.

**Pendiente:** el link real de Stripe Checkout (F4.6) todavía no existe, así que una reserva `stripe` queda en `PENDING_PAYMENT` sin nada que enviarle al cliente todavía más que el correo de "pendiente de pago" genérico.

## 2026-09-13 — F6.5: acciones sobre la reserva (confirmar, pagos, cancelar, reenviar, borrar)

Con el listado de F6.4 ya se podía ver una reserva; F6.5 es poder hacerle algo. Aquí `require_role` (F6.3) protege por primera vez una ruta de verdad: ver una reserva es cualquier rol, actuar sobre ella es cualquiera menos `viewer`.

**Reusar en vez de duplicar la lógica de pago:** `settle_payment` (antes `_settle`, privada de F4.3/F4.4) ya sabía marcar un pago exitoso y mover la reserva a `PAID` (o a `CONFIRMED` de una vez si era el depósito en efectivo) sin nada específico de Stripe adentro. Para que el admin pudiera registrar un pago recibido por transferencia, efectivo o cuenta, bastó con crear el `Payment` con el `provider` que corresponda (el modelo ya tenía `received_by_admin_id`, pensado exactamente para esto) y llamarla igual. Se le agregó un `admin_user_id` opcional para que la auditoría del cambio de estado quede a nombre de quien lo hizo, no solo como "admin" genérico. `_notify_paid` pasó a llamarse `notify_confirmation` y `_amount` a `amount_due`: dejaron de ser privadas de `payments.py` porque ahora también las usa `admin_actions.py`.

**La transición que no estaba en el diagrama:** `mark-unpaid` (§7.2) no tiene ningún renglón en la tabla de §8.2 — ni siquiera `PENDING_PAYMENT` aparecía como destino desde `PAID`. Como corregir un `mark-paid` marcado por error es una necesidad real (y `mark-unpaid` está en la lista de rutas del propio WORKPLAN), se agregó `PAID → PENDING_PAYMENT` a `TRANSITIONS`, documentada en el código, en §8.2 y en el test de la tabla completa (`test_booking_state.py`) como una excepción a propósito. Se limitó a pagos manuales: si el último pago fue de Stripe, `mark-unpaid` responde `manual_payment_required` — deshacer un cobro de verdad es un reembolso, no un borrador de estado.

**Cancelar con reembolso** reusa `create_refund` de `stripe_gateway.py` (ya existía desde F4.1) y actualiza el `Payment` con la misma lógica que el webhook `charge.refunded` (F4.4) aplica cuando Stripe confirma el reembolso por su cuenta — llegar por los dos caminos dejaría el mismo resultado. Reembolsar sin pago de Stripe (`nothing_to_refund`) o sobre un pago manual (`manual_refund_required`) se rechaza explícitamente: efectivo y transferencias se reembolsan fuera del sistema.

**`resend-confirmation`** no es una transición de estado — solo repite el correo que le tocaba al estado actual (`booking_pending_payment` si sigue esperando el pago, si no `notify_confirmation`). Cancelada no tiene nada que reenviar (`nothing_to_resend`).

**Un bug real que encontraron los tests, no yo:** `admin_booking()` (la dependencia que carga la reserva por id) usaba `session.get(Booking, id, options=[selectinload(...)])` — pero `Session.get()` con una fila que ya está en el identity map de la transacción **ignora** los `options`, porque no vuelve a ejecutar ninguna consulta. Una reserva creada dentro del mismo test (sin pasar antes por un `select()` con `selectinload`) reventaba con `'Booking.legs' is not available due to lazy='raise_on_sql'` al construir el detalle. Se cambió a `select(Booking).options(...).where(Booking.id == id)` vía `session.scalar()` — el mismo patrón que ya usaba `managed_booking()` en la API pública, que por eso nunca lo sufrió.

**Archivos:** `backend/app/services/payments.py`, `backend/app/services/bookings.py`, `backend/app/services/booking_state.py`, `backend/app/services/admin_actions.py` (nuevo), `backend/app/schemas/admin_bookings.py`, `backend/app/api/v1/admin/bookings.py`, `backend/tests/test_booking_state.py`, `backend/tests/test_admin_booking_actions.py` (nuevo), `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **238 passed** (15 nuevos): confirmar mueve `OFFLINE_HOLD` a `CONFIRMED` y rechaza `PENDING_PAYMENT` con 409; marcar pagada mueve a `PAID` (o a `CONFIRMED` directo si era depósito en efectivo) y rechaza una reserva que no está esperando pago; deshacer el pago revierte uno manual y rechaza uno de Stripe; cancelar con reembolso llama a Stripe (`respx`) y dejar el pago `REFUNDED`, sin pago que reembolsar o con un pago manual se rechaza; reenviar la confirmación encola el correo otra vez; borrar oculta la reserva del listado y del detalle (404); sin el header CSRF, 403; el rol `viewer` no puede cancelar, 403; el timeline muestra qué admin confirmó la reserva.
- `uv run ruff format --check . && uv run ruff check .` → sin errores. `uv run mypy app scripts` → sin errores.
- `uv run alembic check` (sin migración: F6.5 no toca el esquema, solo la tabla de transiciones en código) y `uv run pip-audit` → sin diferencias ni vulnerabilidades.
- `npm run gen && npm run check` en `packages/api-client` → contrato regenerado, `tsc` sin errores.

**Pendiente:** F6.6 (reserva manual del admin) es lo siguiente; el link de pago de Stripe para una reserva ya creada (parte de F4.6) todavía no existe.

## 2026-09-13 — F6.4: `GET /admin/bookings`, la primera ruta de negocio del admin

Con sesión, TOTP y CSRF listos, tocaba la primera ruta que de verdad sirve al equipo: el listado de reservas. Es la puerta de entrada al resto de F6 (acciones, despacho, dashboard todos parten de aquí) y cierra el riesgo E1 del WORKPLAN ("reserva creada que no aparece en el admin").

**Por qué todos los estados por defecto:** el criterio del WORKPLAN es literal — sin ningún filtro de estado en la URL, la consulta no agrega ningún `WHERE status = ...` propio. Una reserva en `pending_payment` (tarjeta) o recién `confirmed` (efectivo sin depósito) aparece igual que una `cancelled` de hace un año, porque el admin decide qué esconder, no la API.

**El problema de `service_date`:** no es una columna de `bookings` — los traslados la llevan en cada `booking_leg` y las actividades en su `booking_item` (una reserva puede no tener tramos). Se resolvió con una subconsulta correlacionada: `UNION ALL` de las fechas de tramos e ítems de esa reserva, `MIN()` de las dos. Se usa igual para filtrar (`service_from`/`service_to`) y para ordenar (`sort=service_date`), así que solo existe una definición de "la fecha de servicio de una reserva" en todo el sistema.

**Filtro de zona, no por texto:** `booking_legs.origin`/`destination` son el nombre del hotel congelado en texto (para que un hotel renombrado después no cambie reservas viejas), así que filtrar por zona no compara ese texto — hace `booking_legs.hotel_id → hotels.zone_id → zones.slug`. Es exacto y no se rompe si el nombre del hotel tiene acentos o mayúsculas distintas.

**`app/services/admin_bookings.py`** (nuevo): `BookingFilters` (estado, origen, método de pago, zona, rango de fecha de servicio y de creación, y `q` de búsqueda libre) y `list_bookings()`, que arma la consulta con `Customer` ya unido (nombre, email, teléfono salen de ahí) y aplica cada filtro solo si viene puesto. La búsqueda (`q`) compara código, nombre, email y teléfono con `ILIKE`, más un `booking_id IN (...)` contra los tramos cuyo `flight_number` coincide — un solo campo de texto libre cubre las cinco columnas que pedía el WORKPLAN. Paginación con `page`/`page_size` (tope 100) y orden por `created_at`, `service_date` o `total_cents`.

**`GET /api/v1/admin/bookings`** (nuevo router `app/api/v1/admin/bookings.py`): solo pide sesión (`CurrentAdmin`, cualquier rol — ver es distinto de editar, que llega en F6.5 con `require_role`); es un `GET`, así que no necesita el header CSRF.

**Archivos:** `backend/app/services/admin_bookings.py`, `backend/app/schemas/admin_bookings.py`, `backend/app/api/v1/admin/bookings.py`, `backend/app/main.py`, `backend/tests/test_admin_bookings.py`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **223 passed** (8 nuevos): una reserva con tarjeta o en efectivo sin depósito aparece sin ningún filtro de estado (el criterio literal de F6.4); el filtro de estado separa `pending_payment` de `confirmed`; la búsqueda encuentra la reserva por código, apellido, email, teléfono y número de vuelo, y no encuentra nada con un texto que no existe; el filtro de zona encuentra la reserva por el hotel (`the-corridor`) y no la encuentra en otra zona; la paginación de 2 en 2 no repite ni se salta reservas entre páginas; el orden por `total_cents` ascendente deja la reserva barata antes que la cara; sin sesión, 401.
- `uv run ruff format --check . && uv run ruff check .` → sin errores. `uv run mypy app scripts` → sin errores.
- `uv run alembic check` (sin migración: F6.4 no toca el esquema) y `uv run pip-audit` → sin diferencias ni vulnerabilidades.
- `npm run gen && npm run check` en `packages/api-client` → contrato regenerado, `tsc` sin errores.

**Pendiente:** F6.5 (acciones sobre la reserva del §7.2) es lo próximo — ahí `require_role` por fin protege algo de verdad, porque no todas las acciones las puede hacer cualquier rol.

## 2026-09-13 — F6.3: CSRF de doble token y middleware de roles

Seguido de F6.1/F6.2: antes de construir la primera ruta de negocio del admin (F6.4) convenía cerrar la protección contra CSRF, porque agregarla después habría significado tocar cada mutación otra vez.

**Cómo quedó el doble token:** al iniciar sesión (login sin TOTP o `verify_totp`) se ponen dos cookies con el mismo `max_age` de 12 h: `ctc_admin_session` (`HttpOnly`, como ya estaba) y `ctc_admin_csrf` — esta nueva, a propósito **sin** `HttpOnly`, porque el patrón de doble envío exige que el JS del admin la pueda leer para repetirla en el header `X-CSRF-Token` de cada mutación. `require_csrf` (nuevo, `app/api/v1/admin/deps.py`) deja pasar `GET`/`HEAD`/`OPTIONS` sin pedir nada, y en cualquier otro método exige que el header exista, sea igual a la cookie, **y** que su hash coincida con `csrf_hash` de la sesión activa — la tercera condición es la que de verdad protege: una página ajena no puede leer la cookie (mismo origen), pero tampoco podría inventar un valor que coincidiera con el hash guardado aunque de alguna forma adivinara la cookie.

**`app/services/admin_auth.py`, refactor:** `admin_from_session_token` se partió en `session_for_token` (regresa la fila `AdminSession`, no solo el `AdminUser`) porque `require_csrf` necesita `csrf_hash`, que vive ahí. `current_admin` (F6.1) ahora depende de `current_admin_session` en vez de repetir la búsqueda. `revoke_session(token)` se volvió `revoke(admin_session)`, ya que el logout pasó a depender de la sesión ya cargada (`CurrentAdminSession`) en vez de releer la cookie a mano.

**`require_role(*roles)`** (nuevo, mismo archivo): dependencia reutilizable — 403 si el rol del admin no está en la lista. Todavía no protege ninguna ruta real porque F6.4 es la primera; queda lista para entonces. Se probó llamándola directamente con un `AdminUser` de mentira (sin pasar por la base ni por HTTP), ya que no tiene sentido montar una ruta de prueba solo para ejercitar una función pura.

**`POST /admin/auth/logout`** es, por ahora, la única mutación autenticada que existe, así que es la que prueba el criterio de verificación de F6.3 ("POST sin header → 403"). `/login` y `/totp/verify` quedan fuera del CSRF a propósito: son el paso *antes* de tener sesión, no hay cookie de CSRF que exigir todavía.

**Archivos:** `backend/app/services/admin_auth.py`, `backend/app/api/v1/admin/deps.py`, `backend/app/api/v1/admin/auth.py`, `backend/tests/test_admin_auth.py`, `backend/tests/test_admin_csrf.py`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **215 passed** (5 nuevos en `test_admin_csrf.py`, más los 11 de F6.1/F6.2 ajustados para mandar el header en cada `/logout`): un POST autenticado sin `X-CSRF-Token` → 403; con un valor que no coincide con la cookie → 403; con el valor correcto → 204 y de verdad cierra la sesión; un `GET` no necesita el header; `require_role` deja pasar el rol permitido y bloquea los demás con 403.
- `uv run ruff format --check . && uv run ruff check .` → sin errores. `uv run mypy app scripts` → sin errores.
- `uv run alembic check` (sin migración nueva: F6.3 no toca el esquema) y `uv run pip-audit` → sin diferencias ni vulnerabilidades.
- `npm run gen && npm run check` en `packages/api-client` → contrato regenerado, `tsc` sin errores.

**Pendiente:** `require_role` no se ejercita todavía contra una ruta HTTP real — eso llega con F6.4, la primera ruta de negocio del admin.

## 2026-09-13 — F6.1 y F6.2: login del admin con Argon2id y TOTP obligatorio

Con F5 cerrado en lo que no depende de una tarea programada, seguí con F6 porque desbloquea F4.6-F4.8 y F5.9. Hice F6.1 y F6.2 juntos: no tenía sentido dejar un login sin la doble autenticación que el mismo §11 exige para `owner`/`manager`.

**`app/models/admin.py`:** se agregó `totp_backup_codes` (`ARRAY(String(64))`, hashes SHA-256) a `AdminUser`. El resto del modelo (`failed_logins`, `locked_until`, `totp_secret`, y `AdminSession` con solo hashes del token y del CSRF) ya existía de F1.

**`app/services/admin_auth.py`** (nuevo), login en dos pasos cuando el rol lo exige:
- `login(email, password)`: contraseña incorrecta → `invalid_credentials` (401) y **no** revela si el email existe. Al 5.º fallo pone `locked_until` 15 min adelante; el 6.º intento ni llega a `verify_password`, lo corta `locked_until` con `account_locked` (423) — así es el 6.º intento, no el 5.º, el que sale bloqueado, tal como pide el criterio de verificación.
- Si el rol es `owner` o `manager` y no tiene `totp_secret`: genera un secreto TOTP nuevo (`pyotp.random_base32()`) y regresa `totp_setup_required` con la URI `otpauth://` (para el QR) y un `challenge_token` firmado de 5 min que lleva el secreto **sin guardarlo todavía** — un QR nunca escaneado no deja nada a medias en la cuenta.
- Si ya tiene `totp_secret`: `totp_required` con un `challenge_token` sin secreto (ya está guardado).
- Roles sin TOTP obligatorio (`dispatcher`, `finance`, `viewer`): sesión de una vez.
- `verify_totp(challenge_token, code)`: si el token traía un secreto nuevo, lo valida y recién ahí lo persiste junto con 8 códigos de respaldo (`XXXX-XXXX`, se muestran una sola vez, se guardan hasheados); si no, valida contra el secreto ya guardado o consume un código de respaldo (se borra de la lista al usarlo). Cada intento, éxito o fallo, deja un `AuditLog` (reutiliza el modelo de F1.8, actor `ADMIN`, entidad `admin_user`).
- Sesión de servidor: token y CSRF son valores al azar (`secrets.token_urlsafe(32)`); solo sus hashes SHA-256 (`hash_token()`, nuevo en `core/security.py`) van a la tabla `sessions`. Cookie `ctc_admin_session`, `HttpOnly`, `SameSite=Lax`, `Secure` fuera de development/test, 12 h.

**`app/api/v1/admin/`** (nuevo paquete): `auth.py` con `POST /admin/auth/login`, `POST /admin/auth/totp/verify`, `POST /admin/auth/logout` y `GET /admin/auth/me`; `deps.py` con `current_admin`/`CurrentAdmin`, que depende de `CurrentCompany` (fija `session.info["company_id"]` antes de buscar la sesión, igual que el resto de la API — de momento hay una sola empresa, D10).

**Decisión: CSRF y roles quedan fuera de F6.1/F6.2.** El login ya entrega un `csrf_token` y la tabla `sessions` ya guarda su hash, pero nada todavía lo exige en un header ni bloquea por rol — eso es F6.3, a propósito, porque F6.1/F6.2 son sobre login y TOTP, no sobre lo que protege una vez adentro. No hay ninguna ruta de negocio del admin todavía que necesite esa protección.

**Archivos:** `backend/app/models/admin.py`, `backend/app/core/security.py`, `backend/app/services/admin_auth.py`, `backend/app/schemas/admin_auth.py`, `backend/app/api/v1/admin/__init__.py`, `backend/app/api/v1/admin/deps.py`, `backend/app/api/v1/admin/auth.py`, `backend/app/main.py`, `backend/tests/test_admin_auth.py`, `backend/alembic/versions/20260913_9d88d124a402_codigos_de_respaldo_totp_del_admin.py`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **210 passed** (11 nuevos): contraseña incorrecta y email desconocido dan el mismo error; el 6.º intento fallido bloquea incluso con la contraseña correcta; `owner` sin TOTP recibe `totp_setup_required` con la URI y sin cookie; completar el alta entrega sesión y 8 códigos de respaldo; un segundo login del mismo `owner` ya solo pide `totp_required`; un código TOTP incorrecto se rechaza; un código de respaldo entra una vez y la segunda es rechazado; `/me` sin cookie es 401 y con sesión trae el email y el rol; `/logout` revoca la sesión.
- `uv run ruff format --check . && uv run ruff check .` → sin errores. `uv run mypy app scripts` (mismo alcance que el CI) → sin errores.
- `uv run alembic check` → sin diferencias. `uv run pip-audit` → sin vulnerabilidades.
- `npm run gen && npm run check` en `packages/api-client` → contrato regenerado, `tsc` sin errores.

**Pendiente:** F6.3 (CSRF de doble token y middleware de roles) antes de construir cualquier endpoint de negocio del admin.

## 2026-09-13 — F5.1-F5.6, F5.10 y F4.5: cola de correos con Resend

Con F4 ya cobrando bien, seguí con F5 para desbloquear F4.5 (los correos que faltaban al confirmar un pago) sin esperar al admin.

**`app/services/resend_gateway.py`** (nuevo), igual de fino que `stripe_gateway.py`: un `POST /emails` con `from`, `to`, `subject`, `html` y `text`; error de red o rechazo de Resend → `EmailSendError`.

**`app/services/email.py`** (F5.2): `enqueue(session, company_id, template, to, context, language, booking_id)` inserta en `email_outbox`. `company_id` explícito porque el webhook de Stripe no pasa por `get_company` (no hay `session.info` con la empresa ahí).

**`app/templates/emails.py`** (F5.3): diez plantillas en `f-strings` (sin Jinja ni MJML, son correos cortos): `booking_pending_payment`, `booking_confirmed`, `booking_changed`, `booking_cancelled` y `contact_ack` bilingües para el cliente; `booking_new`, `booking_paid_ops`, `booking_changed_ops`, `booking_cancelled_ops` y `contact_lead` en inglés para el equipo de CTC (decisión: los correos internos no necesitan español). Cada una da `(asunto, html, texto plano)`.

**`app/worker/send_emails.py`** (F5.1): `SELECT ... FOR UPDATE SKIP LOCKED` (20 a la vez, por `next_attempt_at`), reintento exponencial (1, 5, 15, 60, 240 min) y `FAILED` al quinto intento. `uv run python -m app.worker.send_emails` procesa una vez; `--loop` para producción.

**Dónde se encola (F5.4-F5.6, F5.10):**
- Reserva creada: `booking_pending_payment` (tarjeta) o `booking_confirmed` (efectivo sin depósito) al cliente; `booking_new` a `EMAIL_OPS_TO`.
- Pago confirmado o depósito pagado (`_settle()`, compartido por F4.3 y F4.4 — llegar por cualquiera de los dos no duplica el correo): `booking_confirmed` al cliente, `booking_paid_ops` a la empresa. **Esto era F4.5.**
- Cambio y cancelación: `booking_changed`/`_ops` y `booking_cancelled`/`_ops` (con el motivo).
- Formulario de contacto: `contact_ack` al remitente y `contact_lead` a la empresa.

**Decisión: enlace en vez de adjunto (F5.4).** El voucher PDF (F3.8) ya vive detrás del token de la reserva; generarlo de nuevo para adjuntarlo exigiría cargar cliente y `company_settings` en tres lugares distintos (creación, confirmación de pago, webhook sin request), y el webhook ni siquiera tiene esos datos a la mano. El correo de confirmación lleva un link a `/my-trip?code=&token=` (todavía no existe la página; F8.4 la construye) en vez del PDF adjunto.

**Config nueva** (fail-fast en staging/producción, igual que Stripe y Turnstile): `RESEND_API_KEY`, `EMAIL_FROM`, `EMAIL_OPS_TO`, `PUBLIC_WEB_URL`.

**Archivos:** `backend/app/core/config.py`, `backend/app/core/security.py` (`booking_manage_url`), `backend/app/services/email.py`, `backend/app/services/resend_gateway.py`, `backend/app/services/bookings.py`, `backend/app/services/payments.py`, `backend/app/api/v1/contact.py`, `backend/app/templates/__init__.py`, `backend/app/templates/emails.py`, `backend/app/worker/__init__.py`, `backend/app/worker/send_emails.py`, `backend/tests/test_email_workflow.py`, `backend/tests/test_worker_send_emails.py`, `backend/tests/test_config.py`, `backend/tests/test_contact.py`, `backend/.env.example`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **199 passed** (17 nuevos): las diez plantillas renderizan en los dos idiomas; una reserva con tarjeta encola `booking_pending_payment` + `booking_new`; en efectivo sin depósito, `booking_confirmed` de una vez; confirmar el pago encola `booking_confirmed` + `booking_paid_ops`; cambiar y cancelar encolan sus cuatro correos (con el motivo en la cancelación); el contacto encola acuse y lead; sin `EMAIL_OPS_TO` solo se encola el del cliente; el worker: envío exitoso marca `SENT` con el id de Resend, un rechazo agenda el reintento con el error guardado, al quinto intento pasa a `FAILED`, un correo que no vence todavía no se toca, un error de red también reintenta, y los correos ya `SENT`/`FAILED`/`SENDING` nunca se vuelven a tomar.
- `ruff`, `mypy`, `alembic check`, `pip-audit` y `tsc` del cliente → sin errores.

**Pendiente:** F5.7 (recordatorio 24 h) y F5.8 (solicitud de reseña) piden una tarea programada; F5.9 (aviso al chofer) espera el despacho del admin (F6); F5.11 (webhooks de Resend) para marcar entregado o rebotado.

## 2026-09-13 — F4.4: webhook de Stripe

**`POST /api/v1/webhooks/stripe`** (nuevo router `app/api/v1/webhooks.py`):
- Firma verificada con `verify_webhook` (F4.1) sobre el cuerpo crudo (`await request.body()`, sin volver a serializarlo: la firma es sobre esos bytes exactos). Firma inválida → 400 `invalid_signature` (lo maneja el handler global de `AppError`, sin código de más).
- `stripe_events` con el id del evento como llave primaria: `INSERT ... ON CONFLICT DO NOTHING`; si ya existía, no se procesa de nuevo (el evento se guarda una sola vez, se procesa una sola vez).
- Sin `get_company`: el webhook llega antes de saber la empresa, y el `Payment` se busca globalmente por `stripe_payment_intent_id` (único).

**`app/services/payments.py`, refactor:** la parte de F4.3 que marca pagado (`payment.status = SUCCEEDED`, `PENDING_PAYMENT → PAID`, y `→ CONFIRMED` si era el depósito en efectivo) se movió a `_settle()`, compartida entre `confirm_payment` (navegador) y el webhook. Así llegar por los dos caminos al mismo pago no lo procesa dos veces: si la confirmación rápida ya marcó `SUCCEEDED`, `_apply_success` no vuelve a tocar la reserva.
- `payment_intent.payment_failed`: marca el `Payment` `FAILED` si seguía `PENDING`; la reserva no cambia (el cliente puede reintentar).
- `charge.refunded`: `refunded_cents` (limitado al monto pagado) y `REFUNDED` o `PARTIALLY_REFUNDED` según alcance. No mueve el estado de la reserva por sí solo — eso lo decide el admin en F4.7.
- `checkout.session.completed` se reconoce (no cae como evento desconocido) pero no hace nada: no existe todavía quien cree esas sesiones (F4.6, link de pago del admin).

**Archivos:** `backend/app/api/v1/webhooks.py`, `backend/app/main.py`, `backend/app/services/payments.py`, `backend/tests/test_webhooks.py`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **182 passed** (8 nuevos): firma inválida → 400; `payment_intent.succeeded` marca `PAID`; el mismo id de evento dos veces solo deja un registro en `stripe_events`; el depósito en efectivo confirma (`CONFIRMED`) igual que por el navegador; si el navegador ya confirmó, el webhook no reintenta la transición; `payment_intent.payment_failed` marca el pago sin tocar la reserva; `charge.refunded` deja el pago reembolsado; un tipo de evento no manejado se guarda igual.
- `ruff`, `mypy`, `alembic check`, `pip-audit` y `tsc` del cliente → sin errores.

**Pendiente:** F4.5 espera al worker de correos (F5); F4.6 a F4.8 esperan al admin (F6); F4.10 (prueba real con Stripe CLI) espera las llaves de prueba del cliente.

## 2026-09-13 — F4.2 y F4.3: crear y confirmar el pago con Stripe

**`app/services/payments.py`** (nuevo), usando el `stripe_gateway.py` de F4.1 sin agregarle lógica:
- `create_or_reuse_intent`: si la reserva no está `pending_payment` → `not_payable` (400). El monto es el depósito (`booking.deposit_cents`) si el pago es en efectivo, o el total si es con tarjeta. Si ya hay un `Payment` `PENDING` de esta reserva, se reconsulta ese mismo intent en Stripe (mismo `client_secret`, cero intents nuevos); si no, se crea uno con una `Idempotency-Key` por reserva y se guarda el `Payment`.
- `confirm_payment`: busca el `Payment` **de esa reserva** por `payment_intent_id` — si no aparece (es de otra reserva o no existe), 400 sin llamar a Stripe. Si aparece, consulta el intent y valida metadata (`booking_id`, `company_id`), monto, moneda y `status == "succeeded"`. Pasa la reserva a `PAID`; si el pago era el depósito en efectivo, de una vez a `CONFIRMED` (dos saltos permitidos por la máquina de estados: `PENDING_PAYMENT → PAID → CONFIRMED`, sin tocar la tabla de §8.2).

**API**, anidada bajo `/bookings/{code}` para reutilizar `ManagedBooking` (el mismo token de reserva) en vez de recibir el código en el body como sugería el mapa de rutas de §7.1 — se actualizó esa tabla:
- `POST /bookings/{code}/payments/intent` → `{"client_secret": "..."}`.
- `POST /bookings/{code}/payments/confirm` → `{"payment_intent_id": "pi_..."}`, responde el detalle de la reserva ya actualizado.
- Dependencia `Stripe` en `deps.py`: un `StripeGateway` por request, cerrado al terminar.

**Esquema:** `bookings.deposit_cents` (antes se calculaba pero no se guardaba); el CHECK `ck_bookings_totals` ahora también exige `deposit_cents >= 0` (autogenerate no detecta cambios de CHECK, se escribió a mano). Migración `0e5b48905a6c`.

**F4.9 queda completa de punta a punta:** la decisión de impuestos y efectivo (D-P5) ya se cobra correctamente con Stripe real, no solo en el motor de precios.

**Archivos:** `backend/alembic/versions/20260913_0e5b48905a6c_deposito_de_la_reserva_para_el_pago_con_.py`, `backend/app/api/deps.py`, `backend/app/api/v1/bookings.py`, `backend/app/models/booking.py`, `backend/app/schemas/bookings.py`, `backend/app/services/bookings.py`, `backend/app/services/payments.py`, `backend/tests/test_payments.py`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **174 passed** (6 nuevos): el segundo `POST /payments/intent` no vuelve a llamar a Stripe y da el mismo `client_secret`; el monto es el depósito en Escalade; confirmar marca `PAID` y una segunda confirmación → `not_payable`; el depósito en efectivo confirma (`CONFIRMED`) en vez de `PAID`; el intent de otra reserva → `payment_mismatch`; una reserva ya cancelada no admite pago.
- `ruff`, `mypy`, `alembic check`, `pip-audit` y `tsc` del cliente → sin errores.

**Pendiente:** F4.4 (webhook, la fuente de verdad si el navegador se cierra antes de confirmar), F4.5 a F4.8 (correos, link de pago del admin, reembolsos, pagos manuales), F4.10 (prueba con Stripe CLI, necesita las llaves de prueba del cliente).

## 2026-09-13 — F3.12, F3.13 y F4.9: formulario de reserva y pago en efectivo como All Ways

Continuación de la réplica de la referencia (§3.5), ahora en el formulario de reserva y el pago.

**Cliente (`CustomerIn`)**
- `first_name` y `last_name` en vez de un solo `name` (se combinan al guardar el `Customer`, sin migrar la tabla).
- `confirm_email`: debe coincidir con `email` sin importar mayúsculas, si no → "Emails don't match" (mismo texto que la referencia).
- `phone` pasa de opcional a obligatorio (mínimo 7 caracteres), igual que "Mobile phone \*".

**Hora de pickup editable**
- `LegIn.pickup_time`: si el cliente la manda, se usa esa hora (ajustando la fecha si cruza medianoche) en vez de la sugerida automática (3 h internacional, 2 h nacional); si no la manda, sigue igual que antes. La anticipación mínima se valida sobre la hora que quede.

**Aceptación de términos**
- `company_settings.terms_version` (nueva, default "1") y `accepted_terms_version` obligatorio en la reserva; si no coincide → `terms_outdated`. La fecha de aceptación es `bookings.created_at`; no hacía falta una columna aparte.

**Pago en efectivo (F3.13, y decide F4.9)**
- `bookings.payment_method` ("card" o "cash") para mostrarlo en el voucher y, más adelante, en el admin.
- Efectivo sin depósito (todos los vehículos salvo Escalade y Limousine) → la reserva se crea directamente `CONFIRMED`, sin pasar por pago en línea, igual que "Cash on Arrival" allá.
- Efectivo con depósito (Escalade, Limousine) → sigue `PENDING_PAYMENT`; cobrar y confirmar el depósito con tarjeta es trabajo de F4.2/F4.3 (Stripe), no de este motor.
- Voucher: reservas en efectivo muestran "Balance payable in cash on arrival" / "Saldo a pagar en efectivo a la llegada" por el total completo.
- **F4.9 (D-P5) se marca hecha:** la regla de impuestos y efectivo que pedía esa tarea ya está implementada de punta a punta (motor de precios + estado de la reserva), aunque cobrar el depósito en sí es tarea de Stripe.

**Archivos:** `backend/alembic/versions/20260913_0d1e992bc78d_terminos_y_metodo_de_pago_en_reservas.py`, `backend/app/models/booking.py`, `backend/app/models/company.py`, `backend/app/schemas/bookings.py`, `backend/app/schemas/quotes.py`, `backend/app/services/bookings.py`, `backend/app/services/voucher.py`, `backend/tests/test_bookings.py`, `backend/tests/test_booking_access.py`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **168 passed** (5 nuevos): hora de pickup editada se respeta; email y confirmación distintos → 422 con el mensaje de la referencia; teléfono corto o ausente → 422; versión de términos vieja → `terms_outdated`; efectivo sin depósito confirma sin IVA, con depósito (Escalade) sigue pendiente, tarjeta sigue pendiente con IVA.
- `ruff`, `mypy`, `alembic check`, `pip-audit` y `tsc` del cliente → sin errores.

**Pendiente:** Return Time en traslados locales redondos, y Local One Way/Round Trip, chofer por hora y city tour como tipos de reserva — necesitan el schema nuevo de F2.12 (sin hotel de origen/destino). El estado "Deposit Paid" real llega con Stripe (F4.2, F4.3).

## 2026-09-13 — F2.10 y F2.11: catálogo y motor de precios iguales a All Ways

Marlon confirmó "todo igual, adelante": se reemplaza el catálogo de ClassVIP por el de allwayscabotransportation.com (D-P1, D-P8, D-P14 ya decididas en el WORKPLAN) y el motor cotiza por unidades en vez de rechazar grupos grandes.

**Catálogo (`scripts/data/catalog.json`, `scripts/gen_catalog.py` en el scratchpad de la sesión, no versionado)**
- 10 zonas con nombres y slugs propios (§3.5.6), reemplazando las 6 de ClassVIP.
- 5 vehículos con los campos nuevos de la referencia: `included_pax`, `extra_pax_cents` (limusina), `extra_hour_cents` (recargo nocturno) y `cash_deposit_cents`.
- 180 tarifas (10 zonas × 5 vehículos × ida/redondo × aeropuerto/local, menos la limusina fuera de las zonas 1–5).
- 8 extras con `free_qty` (primera silla y primer booster gratis), `vehicle_prices` (parada en súper distinta en Escalade) y `one_per_vehicle`.
- 226 hoteles reasignados a las 10 zonas: se descargó `/api/booking/places` de la referencia (520 lugares) y se cruzó por nombre normalizado — 76 coincidencias exactas, 58 por nombre corto sin palabras de relleno (hotel, resort, spa…) y 8 por similitud ≥ 0.86; los 84 restantes por la zona real del hotel (documentado en `meta.hotel_zone_decisions`).
- `seed_catalog.py` ahora desactiva (`is_active=False`) zonas, vehículos y extras que salen del JSON en vez de dejarlos huérfanos.

**Motor de precios (`app/services/pricing.py`, reescrito)**
- `_vehicle_and_rate`: si no se pide un vehículo, se cotizan todos los que tengan tarifa en esa zona/viaje y se toma el de menor total (no el de menor capacidad).
- `_units`: `ceil(pasajeros / max_pax)`; ya no hay `too_many_passengers` ni `vehicle_too_small`. El límite de pasajeros bajó de 50 a 20 en el schema, igual que el stepper de la referencia.
- Pasajeros extra de limusina después de `included_pax` (6), por unidad y por tramo.
- Extras: unidades gratis primero, luego precio por vehículo si existe, y `extra_per_vehicle` si `one_per_vehicle` no alcanza para las unidades pedidas.
- `night_hours()` reemplaza a `in_night_window()`: cuenta horas nocturnas exactas (75 min el primer bloque, luego una hora por cada hora iniciada) en vez de un sí/no; se multiplica por `extra_hour_cents` del vehículo. **Decisión propia, documentada en ADR-002:** en redondo se suman las horas nocturnas de los dos tramos, aunque el código de la referencia solo cuenta el regreso cuando ambos son nocturnos (parece un error de ellos).
- IVA 16% (`company_settings.card_tax_percent`) con tarjeta sobre subtotal − descuento; sin IVA en efectivo ni en salidas al aeropuerto (`cash_unavailable` si se pide efectivo en una salida).
- Depósito con tarjeta al pagar en efectivo en Escalade y Limousine.

**Esquema:** `booking_legs.vehicle_count` y `booking_assignments.unit_index` (única por `leg_id, unit_index`; antes era única solo por `leg_id`, lo que impedía dos choferes en el mismo tramo). Migración `a669171fe543`.

**Investigación:** las fórmulas de recargo nocturno, pasajeros extra de limusina y depósito no estaban en el HTML visible; se sacaron leyendo `dep_BlockConflictModal-*.js`, el chunk que de verdad calcula el precio en el frontend de la referencia (descargado con curl y un User-Agent de navegador, igual que en la sesión anterior).

**Archivos:** `backend/app/models/catalog.py`, `backend/app/models/company.py`, `backend/app/models/booking.py`, `backend/app/models/operations.py`, `backend/app/schemas/catalog.py`, `backend/app/schemas/quotes.py`, `backend/app/schemas/bookings.py`, `backend/app/services/pricing.py`, `backend/app/services/bookings.py`, `backend/scripts/seed_catalog.py`, `backend/scripts/data/catalog.json`, `backend/alembic/versions/20260912_a669171fe543_*.py`, `backend/tests/test_pricing.py` (reescrito), `backend/tests/test_bookings.py`, `backend/tests/test_seed_catalog.py`, `backend/tests/test_api_public.py`, `backend/tests/test_hotel_search.py`, `backend/tests/test_models_operations.py`, `docs/decisions/ADR-002-precios.md` (reescrito), `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **163 passed**: cada celda de la matriz de tarifas contra el catálogo (con `rate_unavailable` donde la limusina no opera), "Any type of Vehicle" toma el menor total, 8 y 20 pasajeros piden 2 unidades y cobran el doble, 21 pasajeros → `ValidationError`, limusina cobra pasajeros extra por tramo, sillas de auto gratis y de pago, parada en súper con precio de Escalade y la regla de una por vehículo, horas nocturnas exactas (23:00→1, 00:15→2, 04:59→6, 05:00→0) multiplicadas por la tarifa del vehículo, promo de septiembre sobre la base de todas las unidades, IVA con tarjeta y depósito en efectivo, el seed retira lo que ya no está en el catálogo.
- `ruff`, `ruff format`, `mypy`, `alembic check`, `pip-audit` y `tsc` del cliente → sin errores.

**Pendiente:** F2.9 (Marlon revisa el ADR-002), F2.12 (chofer por hora y activity transfers como tipos de servicio cotizables — piden un schema nuevo porque no tienen hotel de origen/destino) y F3.12/F3.13 (campos del formulario de reserva y flujo de pago en efectivo iguales a la referencia).

## 2026-09-12 — Diferenciación de All Ways y logo oficial de CTC

Marlon pidió que el diseño quede más premium y no tan igual a All Ways: otras fuentes, navbar algo distinto, zonas y textos parecidos pero diferentes, y usar su logo.

**WORKPLAN §3.5.6** (commit `eaf55d2`)
- Logo oficial en todo el sistema.
- Tipografías Cormorant Garamond, Cinzel y Manrope (Marlon aprueba muestras en F7.2).
- Navbar con barra superior, medallón centrado, barra compacta de vidrio y mega menú de ancho completo.
- Nombres y slugs propios para las 10 zonas en EN y ES.
- Regla de textos reescritos con verificación de similitud.
- F7.2, F7.4 y F2.10 ajustadas; F7.16 nueva. AGENTS.md actualizado.

**Logo aplicado**
- Hasta hoy el header del prototipo usaba `logo-ctc.svg`, un emblema provisional dibujado por mí, no el logo del cliente. Ahora usa el medallón oficial (`Downloads\Video\Cabotransportation logo.jpg`).
- `site/images/logo/`:
  - `ctc-medallion-{512,192,128,64}.webp`, más `.png` en 512 y 192, con fondo transparente (recorte circular).
  - `favicon-32.png` con el monograma CTC (el medallón completo no se lee a 32 px).
  - `apple-touch-icon.png`.
- Prototipo:
  - Medallón de 56–64 px en el header y de 160 px en el footer.
  - Favicons, manifest y `msapplication-config` de la referencia eliminados.
  - `theme-color` obsidiana y JSON-LD `logo` con el PNG de 512 px.
  - Se borró `logo-ctc.svg`.
- Las fuentes `original.html` y `arrival-original.html` ya no están en el repo, así que `build.js` no se puede volver a correr. Se actualizó igual (queda como registro de las transformaciones) y los mismos cambios se aplicaron sobre `index.html` y `arrival-guide.html`.
- Voucher PDF: el emblema dibujado a mano se reemplazó por el medallón (`backend/app/assets/ctc-medallion-192.png`).

**Test intermitente corregido:** `test_altered_or_missing_token_is_rejected` alteraba el último carácter del token. En base64url ese carácter a veces solo lleva bits de relleno, así que la firma seguía siendo válida y el test fallaba en algunas corridas. Ahora altera el primero, que siempre cambia el contenido firmado.

**Verificación**
- Capturas headless con Edge a 1440 y 400 px: el medallón se ve en el header.
- Voucher de muestra revisado a la vista.
- `pytest` completo, `ruff` y `mypy` en verde; el test del token pasó 20 de 20 corridas.

**Pendiente:**
- En móvil (400 px), el botón "Book transfer" del header del prototipo se corta por la derecha; se resuelve con el navbar nuevo (F7.4 y F7.14).
- SVG vectorial del logo para pantallas grandes (F7.16).

**Archivos:** `site/build.js`, `site/luxe.css`, `site/index.html`, `site/arrival-guide.html`, `site/images/logo/*`, `site/images/svg/logo-ctc.svg` (borrado), `backend/app/assets/ctc-medallion-192.png`, `backend/app/services/voucher.py`, `backend/tests/test_booking_access.py`

## 2026-09-12 — WORKPLAN v1.2: réplica completa de All Ways con datos propios

Marlon pidió: la página igual a All Ways (servicios, reserva, Bachelorette y City Tours con su propia área, tarifas), diseño más moderno, precios iguales y toda la información de CTC, sin que se pase ningún dato.

**Cómo se levantó la especificación**
- Rutas: el mapa Ziggy de la app (132 rutas públicas).
- Props: el JSON `data-page` de 33 páginas.
- Textos, campos y mensajes: los chunks JS de cada página.
- APIs públicas: `private-driver` y `activity-rates`.

Nada de eso se versiona (es contenido de terceros): solo la especificación escrita.

**Qué se agregó al WORKPLAN**
- §3.5.1: tres reglas (igual en estructura, diseño moderno, cero datos) y lista prohibida con marca, teléfonos, direcciones, marcas hermanas, cifras de reseñas, personas y assets.
- §3.5.2: header, mega menú Services (Airport & Transfers, Events & Groups, Tours) y footer.
- §3.5.3: inventario de 40 rutas con secciones en orden, formularios y datos, y las rutas que no se replican.
- §3.5.4: tarifas completas (10 zonas × 5 vehículos × aeropuerto/local, chofer por hora, activity transfers, extras, depósitos, promo, IVA).
- §3.5.5: motor de reserva paso a paso (Service, Extras, Contact, Payment y Order Summary).
- Decisiones: D-P1 (precios de All Ways), D-P8 (todos los servicios) y D-P14 (multi-vehículo) decididas por el "todo igual"; D-P5 igual a All Ways con revisión del contador; D-P15 nueva (cobro en MXN).
- Tareas: F2.10–F2.12, F3.12–F3.13, F8.14 y F9.16–F9.20. F3 vuelve a quedar abierta (11/13).

**Por verificar en F2.10:** tres montos que el código no mostró con claridad: recargo nocturno por vehículo, orden de las tarifas de activity transfers y cargo por pasajero extra de la limusina.

**Archivos:** `WORKPLAN.md`, `AGENTS.md`

## 2026-09-12 — Verificación del campo "Passengers" en allwayscabotransportation.com/booking

Marlon pidió revisar bien la página real de reserva de All Ways en cuanto a "cuántas personas". Como es una SPA (Inertia + Vue, sin SSR del contenido), leí el JSON de props (`data-page`) y descargué los chunks reales `BookingHome-*.js`, `Vehicle-*.js` y `Payments-*.js` desde `/build/assets/` para confirmar el comportamiento exacto en el código, no solo lo visible.

**Confirmado (antes ya estaba en §3.4.1, ahora con precisión del código real):**
- Un solo campo `pax` (no separa adultos/niños/infantes). Stepper −/+, mínimo 1.
- Tope: escribir más de 19 lo ajusta solo a 20. Es el máximo reservable en línea.

**Nuevo, no documentado antes:** All Ways **no rechaza por capacidad**. Cualquier vehículo se puede elegir con cualquier número de pasajeros: multiplica el precio por `ceil(pasajeros / capacidad)` unidades (Limousine usa `max_capacity`, no `capacity`). 8 pasajeros en un Suburban (capacidad 5) = 2 Suburbans, el doble de precio, no un error.

Aquí el motor (F2.2) rechaza con `too_many_passengers` arriba de 14 (el máximo de la Sprinter, único vehículo grande activo). Igualar el comportamiento de All Ways exige cotizar por unidades, agregar cantidad a `booking_legs` y que el despacho asigne un chofer por unidad (`booking_assignments` hoy tiene `UNIQUE(leg_id)`, una sola asignación por tramo). Es un cambio de esquema, no solo de copy, así que lo dejé como **D-P14** en vez de decidirlo solo. Mientras tanto se mantiene el rechazo con mensaje de contactar por WhatsApp (coincide con el valor por defecto que ya existía).

**Archivos:** `WORKPLAN.md` (§3.4.1, tabla de decisiones pendientes D-P14)

**Pendiente:** que Marlon decida D-P14 (automatizar multi-vehículo como All Ways, o mantener "contáctanos" para grupos grandes).

## 2026-09-12 — F4.1 cliente de Stripe

**Qué se hizo**
- `app/services/stripe_gateway.py`: envoltura fina sobre la API REST de Stripe con httpx, sin SDK y sin lógica de negocio.
  - `create_payment_intent` (monto, moneda en minúsculas, `automatic_payment_methods`, metadata, `receipt_email` opcional) con `Idempotency-Key` obligatoria.
  - `retrieve_payment_intent` y `create_refund` (total o parcial, con idempotencia).
  - Errores: respuesta de Stripe → `StripeError("stripe_error")` con su mensaje; red caída o respuesta ilegible → `stripe_unavailable`. Ambos 502.
  - `verify_webhook`: firma `Stripe-Signature` (HMAC-SHA256 de `t.payload`, varias `v1` aceptadas, comparación en tiempo constante) y tolerancia de 5 minutos → si no, `InvalidSignature` (400).
- Config: `STRIPE_SECRET_KEY` y `STRIPE_WEBHOOK_SECRET`, obligatorias en producción junto con Turnstile.
- `respx` como dependencia de desarrollo para simular Stripe.

**Archivos:** `backend/app/core/config.py`, `backend/app/services/stripe_gateway.py`, `backend/tests/test_config.py`, `backend/tests/test_contact.py`, `backend/tests/test_stripe_gateway.py`, `backend/.env.example`, `backend/pyproject.toml`, `backend/uv.lock`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **155 passed** (4 nuevos):
  - El intent se envía con autenticación, `Idempotency-Key` y el formulario exacto (`metadata[booking_id]`, `automatic_payment_methods[enabled]=true`, `currency=usd`).
  - Un 404 de Stripe → `stripe_error` con su mensaje; un timeout → `stripe_unavailable` (502).
  - Firma válida → evento. Rechazados: cuerpo alterado, firma de hace más de 5 min, otro secreto y encabezado sin timestamp.
  - Producción sin `STRIPE_WEBHOOK_SECRET` no arranca.
- CI del commit anterior (F3 completa) en verde: run `34738195655`.
- `ruff`, `mypy` y `pip-audit` → sin errores.

**Pendiente:** F4.2 a F4.8. Necesito del cliente las llaves de prueba de Stripe (F4.10) y la decisión D-P5 sobre impuestos y efectivo (F4.9).

## 2026-09-12 — F3.8 voucher PDF (F3 completa)

**Qué se hizo**
- `GET /bookings/{code}/voucher.pdf` con el token de la reserva → PDF `inline`, `Cache-Control: private, no-store`. Se dibuja en un hilo (`run_in_threadpool`) para no frenar otros requests.
- `app/services/voucher.py`, formato carta en inglés o español según la reserva:
  - Encabezado con el emblema del logo (vector) y el nombre en dorado.
  - QR del código dibujado como vectores.
  - Código, huésped y estado (traducido).
  - Cada tramo: pickup, ruta, vuelo y pasajeros.
  - Resumen con montos y fecha de actividades.
  - Punto de encuentro (solo si hay llegada) y contacto.
- **Punto de encuentro:** sale de `company_settings.arrival_instructions`. Si está vacío, el voucher remite al correo de confirmación. No se usa el texto del prototipo ("Canopy 3, Island Bar") porque viene de All Ways; el punto real está en el checklist del cliente.

**Decisión: fpdf2 + segno en lugar de WeasyPrint.** WeasyPrint necesita GTK/Pango instalados en el sistema (difícil en Windows y más pesado en Railway). fpdf2 y segno son Python puro, generan un PDF de ~3 KB con texto seleccionable y funcionan igual en local, CI y producción. `pypdf` queda solo para los tests.

**Archivos:** `backend/app/api/v1/bookings.py`, `backend/app/services/bookings.py` (`company_settings` público), `backend/app/services/voucher.py`, `backend/tests/test_voucher.py`, `backend/pyproject.toml`, `backend/uv.lock`, `packages/api-client/src/schema.d.ts`, `WORKPLAN.md`

**Verificación**
- `uv run pytest` → **151 passed** (2 nuevos): el texto extraído del PDF contiene código, "Ana López", hotel, vuelo y "Meeting point"; sin token → 401; token de otra reserva → 404.
- Revisión visual de muestras en inglés y español: encabezado, QR, tramos, resumen y acentos correctos.
- `ruff`, `mypy`, `alembic check`, `pip-audit` y `tsc` → sin errores.

**Pendiente:** F4 (Stripe). Las descripciones de los ítems de traslado salen en inglés ("round trip"); se traducen al hacer bilingüe el motor en F8.

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
