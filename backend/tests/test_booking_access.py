import time

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import BOOKING_TOKEN_SECONDS, booking_token
from tests.test_bookings import URL, _transfer


async def _book(
    api: AsyncClient, db: AsyncSession, email: str = "ana@example.com"
) -> dict[str, str]:
    body = await _transfer(db, customer={"name": "Ana López", "email": email})
    response = await api.post(URL, json=body)
    assert response.status_code == 201, response.text
    created: dict[str, str] = response.json()
    return created


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_token_opens_its_booking(api: AsyncClient, db: AsyncSession) -> None:
    created = await _book(api, db)
    response = await api.get(f"{URL}/{created['code']}", headers=_bearer(created["token"]))
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["total_cents"] == created["total_cents"]
    assert [leg["leg_type"] for leg in detail["legs"]] == ["arrival", "departure"]


async def test_altered_or_missing_token_is_rejected(api: AsyncClient, db: AsyncSession) -> None:
    created = await _book(api, db)
    token = created["token"]
    # El primer carácter siempre cambia el contenido; el último puede ser solo relleno base64.
    altered = ("A" if token[0] != "A" else "B") + token[1:]
    for headers in (_bearer(altered), {}):
        response = await api.get(f"{URL}/{created['code']}", headers=headers)
        assert response.status_code == 401


async def test_token_of_another_booking_is_not_found(api: AsyncClient, db: AsyncSession) -> None:
    first = await _book(api, db)
    second = await _book(api, db, email="luis@example.com")
    response = await api.get(f"{URL}/{second['code']}", headers=_bearer(first["token"]))
    assert response.status_code == 404


async def test_expired_token_is_rejected(
    api: AsyncClient, db: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = await _book(api, db)
    company_id = db.info["company_id"]
    issued = time.time() - BOOKING_TOKEN_SECONDS - 60
    with monkeypatch.context() as past:
        past.setattr(time, "time", lambda: issued)
        old = booking_token(company_id, created["code"])
    response = await api.get(f"{URL}/{created['code']}", headers=_bearer(old))
    assert response.status_code == 401


async def test_lookup_does_not_reveal_which_part_is_wrong(
    api: AsyncClient, db: AsyncSession
) -> None:
    created = await _book(api, db)
    code = created["code"]
    found = await api.get(
        f"{URL}/lookup", params={"code": code.lower(), "email": "ANA@example.com"}
    )
    assert found.status_code == 200
    reopened = await api.get(f"{URL}/{code}", headers=_bearer(found.json()["token"]))
    assert reopened.status_code == 200

    wrong_email = await api.get(f"{URL}/lookup", params={"code": code, "email": "x@example.com"})
    no_booking = await api.get(
        f"{URL}/lookup", params={"code": "CTC-2000-000001", "email": "ana@example.com"}
    )
    assert wrong_email.status_code == no_booking.status_code == 404
    assert wrong_email.json() == no_booking.json()


async def test_lookup_is_rate_limited_harder(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: 120.0)
    params = {"code": "CTC-2000-000001", "email": "ana@example.com"}
    statuses = [(await api.get(f"{URL}/lookup", params=params)).status_code for _ in range(6)]
    assert statuses == [404] * 5 + [429]
