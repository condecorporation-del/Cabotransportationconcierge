import secrets
from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_LOCAL_HOSTS = ("localhost", "127.0.0.1")


class Settings(BaseSettings):
    """Configuración del entorno. En staging y producción no arranca si es insegura."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["development", "test", "staging", "production"] = "development"
    database_url: str = Field(repr=False)
    # Conexión Direct de Supabase: solo para migraciones (WORKPLAN D2). Si falta, usa database_url.
    database_url_direct: str | None = Field(default=None, repr=False)
    secret_key: str = Field(default="", repr=False)
    # Stripe: llaves de prueba en local y staging; live solo en producción.
    stripe_secret_key: str = Field(default="", repr=False)
    stripe_webhook_secret: str = Field(default="", repr=False)
    # Cloudflare Turnstile en formularios públicos; vacía en local = no se exige.
    turnstile_secret_key: str = Field(default="", repr=False)
    # Correos (D7): la API solo encola en email_outbox; app/worker/send_emails.py los envía.
    resend_api_key: str = Field(default="", repr=False)
    # Webhook de Resend (F5.11): firma Svix, "entregado"/"rebotado" en email_outbox.
    resend_webhook_secret: str = Field(default="", repr=False)
    email_from: str = "no-reply@cabotransportationconcierge.com"
    email_ops_to: str = ""
    # Enlaces firmados de la reserva (voucher, My Trip) en los correos.
    public_web_url: str = "https://www.cabotransportationconcierge.com"
    # Empresa que atiende el sitio público mientras haya una sola (WORKPLAN D10).
    default_company_slug: str = "cabo-transportation-concierge"

    @model_validator(mode="after")
    def _fail_fast(self) -> Self:
        if self.environment not in ("staging", "production"):
            # Local sin SECRET_KEY: clave aleatoria; los enlaces firmados valen hasta reiniciar.
            self.secret_key = self.secret_key or secrets.token_urlsafe(48)
            return self
        errors = []
        if len(self.secret_key) < 32:
            errors.append("SECRET_KEY debe tener al menos 32 caracteres")
        if any(host in self.database_url for host in _LOCAL_HOSTS):
            errors.append("DATABASE_URL no puede apuntar a localhost")
        required = {
            "TURNSTILE_SECRET_KEY": self.turnstile_secret_key,
            "STRIPE_SECRET_KEY": self.stripe_secret_key,
            "STRIPE_WEBHOOK_SECRET": self.stripe_webhook_secret,
            "RESEND_API_KEY": self.resend_api_key,
            "RESEND_WEBHOOK_SECRET": self.resend_webhook_secret,
            "EMAIL_OPS_TO": self.email_ops_to,
        }
        errors += [f"{name} es obligatoria" for name, value in required.items() if not value]
        if errors:
            raise ValueError("; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
