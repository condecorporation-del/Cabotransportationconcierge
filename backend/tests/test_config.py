import pytest
from pydantic import ValidationError

from app.core.config import Settings

REMOTE_DB = "postgresql+asyncpg://app:secret@db.example.com:5432/ctc"
STRONG_KEY = "k" * 32
PRODUCTION_SECRETS = {
    "turnstile_secret_key": "turnstile-secret",
    "stripe_secret_key": "sk_live_x",
    "stripe_webhook_secret": "whsec_x",
    "resend_api_key": "re_live_x",
    "resend_webhook_secret": "whsec_resend_x",
    "email_ops_to": "ops@cabotransportationconcierge.com",
}


@pytest.mark.parametrize(
    ("database_url", "secret_key", "error"),
    [
        (REMOTE_DB, "short", "SECRET_KEY"),
        ("postgresql+asyncpg://app:secret@localhost:5432/ctc", STRONG_KEY, "localhost"),
        (REMOTE_DB, STRONG_KEY, "TURNSTILE_SECRET_KEY"),
        (REMOTE_DB, STRONG_KEY, "STRIPE_WEBHOOK_SECRET"),
        (REMOTE_DB, STRONG_KEY, "RESEND_API_KEY"),
        (REMOTE_DB, STRONG_KEY, "RESEND_WEBHOOK_SECRET"),
        (REMOTE_DB, STRONG_KEY, "EMAIL_OPS_TO"),
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


def test_local_without_secret_gets_a_random_strong_key() -> None:
    first, second = (
        Settings(_env_file=None, environment="development", database_url=REMOTE_DB)
        for _ in range(2)
    )
    assert len(first.secret_key) >= 32
    assert first.secret_key != second.secret_key


def test_production_accepts_secure_config_and_hides_secrets() -> None:
    settings = Settings(
        _env_file=None,
        environment="production",
        database_url=REMOTE_DB,
        secret_key=STRONG_KEY,
        **PRODUCTION_SECRETS,
    )
    assert "secret" not in repr(settings)
