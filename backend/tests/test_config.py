import pytest
from pydantic import ValidationError

from app.core.config import Settings

REMOTE_DB = "postgresql+asyncpg://app:secret@db.example.com:5432/ctc"
STRONG_KEY = "k" * 32


@pytest.mark.parametrize(
    ("database_url", "secret_key", "error"),
    [
        (REMOTE_DB, "short", "SECRET_KEY"),
        ("postgresql+asyncpg://app:secret@localhost:5432/ctc", STRONG_KEY, "localhost"),
    ],
)
def test_production_refuses_insecure_config(database_url: str, secret_key: str, error: str) -> None:
    with pytest.raises(ValidationError, match=error):
        Settings(
            _env_file=None,
            environment="production",
            database_url=database_url,
            secret_key=secret_key,
        )


def test_production_accepts_secure_config_and_hides_secrets() -> None:
    settings = Settings(
        _env_file=None, environment="production", database_url=REMOTE_DB, secret_key=STRONG_KEY
    )
    assert "secret" not in repr(settings)
