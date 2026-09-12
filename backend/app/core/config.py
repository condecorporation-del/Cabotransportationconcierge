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
    secret_key: str = Field(default="", repr=False)

    @model_validator(mode="after")
    def _fail_fast(self) -> Self:
        if self.environment not in ("staging", "production"):
            return self
        errors = []
        if len(self.secret_key) < 32:
            errors.append("SECRET_KEY debe tener al menos 32 caracteres")
        if any(host in self.database_url for host in _LOCAL_HOSTS):
            errors.append("DATABASE_URL no puede apuntar a localhost")
        if errors:
            raise ValueError("; ".join(errors))
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
