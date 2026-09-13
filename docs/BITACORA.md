# Bitácora — Cabo Transportation Concierge

Una entrada por sesión o tarea, la más reciente arriba (formato en `AGENTS.md` §10).

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
