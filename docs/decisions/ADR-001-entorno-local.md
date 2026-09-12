# ADR-001 — Entorno local sin Docker

**Fecha:** 2026-09-12 · **Estado:** aceptada · **Modifica:** WORKPLAN §5.2 y §14 (fila Local), tarea F0.5

## Contexto
El WORKPLAN pedía `docker-compose` con Postgres y Mailpit. En la PC de desarrollo no hay Docker y WSL fue desinstalado (Docker Desktop lo necesita).

## Decisión
- **Postgres 16 nativo** de Windows en el puerto 5432 (instalado con winget). La contraseña local vive fuera del repo en `C:\Users\conde\.secrets\cabo-postgres-local.env`.
- Bases: `ctc` para desarrollo y `ctc_test` para pytest.
- **Mailpit** como binario (`mailpit`, UI en http://localhost:8025, SMTP en 1025).
- **Python 3.12 administrado por uv**. El Python 3.14 del sistema no se usa.
- **Seguridad estática con las reglas `S` de ruff** (las mismas de bandit), así no hay una dependencia extra.
- En **CI** Postgres corre como contenedor de servicio de GitHub Actions: los tests siguen siendo contra Postgres real (D13).

## Consecuencias
- No existe `docker-compose.yml`. Si en el futuro se instala Docker, se puede agregar sin tocar el código: solo cambian las URLs del `.env`.
