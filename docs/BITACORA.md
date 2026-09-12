# Bitácora — Cabo Transportation Concierge

Una entrada por sesión o tarea, la más reciente arriba (formato en `AGENTS.md` §10).

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
