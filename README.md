# Cabo Transportation Concierge

Sitio público, reservas, pagos y admin. Qué construir: `WORKPLAN.md`. Reglas de trabajo: `AGENTS.md`.

## Desarrollo local (Windows)

Requisitos: Postgres 16 nativo (puerto 5432), [uv](https://docs.astral.sh/uv/), Node 24 y Mailpit. Ver `docs/decisions/ADR-001-entorno-local.md`.

```powershell
# Backend
cd backend
Copy-Item .env.example .env   # completar DATABASE_URL y TEST_DATABASE_URL
uv sync
uv run pytest
uv run uvicorn app.main:app --reload   # http://localhost:8000/docs

# Cliente de API tipado (después de cambiar endpoints)
cd ..\packages\api-client
npm ci
npm run gen
npm run check
```

`site/` es el prototipo visual aprobado (referencia de diseño): `node site/build.js` lo regenera.
