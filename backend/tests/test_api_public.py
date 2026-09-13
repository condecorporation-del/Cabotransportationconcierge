import uuid
from datetime import date, timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.core.config import get_settings

SOON = (date.today() + timedelta(days=30)).isoformat()


async def _hotel_id(api: AsyncClient, query: str) -> str:
    response = await api.get("/api/v1/catalog/hotels", params={"q": query})
    assert response.status_code == 200, response.text
    return str(response.json()[0]["id"])


def _transfer(hotel_id: str, **changes: Any) -> dict[str, Any]:
    return {
        "type": "transfer",
        "hotel_id": hotel_id,
        "trip_type": "one_way",
        "passengers": 4,
        "legs": [{"service_date": SOON, "service_time": "14:30"}],
    } | changes


async def test_transfer_quote(api: AsyncClient) -> None:
    hotel_id = await _hotel_id(api, "riu palace cabo")
    response = await api.post("/api/v1/quotes", json=_transfer(hotel_id))
    assert response.status_code == 200, response.text
    quote = response.json()
    assert quote["zone"] == "cabo-san-lucas"
    assert quote["lines"][0]["kind"] == "transfer"
    assert quote["total_cents"] == quote["subtotal_cents"] - quote["discount_cents"] > 0


async def test_activity_quote(api: AsyncClient) -> None:
    [package, *_] = (await api.get("/api/v1/catalog/packages")).json()
    activities = [a["slug"] for a in (await api.get("/api/v1/catalog/activities")).json()]
    body = {
        "type": "activity",
        "package": package["slug"],
        "activities": activities[: package["activity_count"]],
        "guests": 2,
        "service_date": SOON,
    }
    response = await api.post("/api/v1/quotes", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["total_cents"] == package["price_per_person_cents"] * 2


async def test_invalid_payload_explains_the_problem(api: AsyncClient) -> None:
    body = _transfer(str(uuid.uuid4()), trip_type="round_trip", passengers=0)
    response = await api.post("/api/v1/quotes", json=body)
    assert response.status_code == 422
    fields = {tuple(error["loc"][-1:]) for error in response.json()["detail"]}
    assert ("passengers",) in fields


async def test_business_errors_have_a_stable_code(api: AsyncClient) -> None:
    response = await api.post("/api/v1/quotes", json=_transfer(str(uuid.uuid4())))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "hotel_not_found"


async def test_catalog_uses_etag(api: AsyncClient) -> None:
    first = await api.get("/api/v1/catalog/zones")
    assert first.status_code == 200
    assert all(zone["from_price_cents"] for zone in first.json())
    second = await api.get(
        "/api/v1/catalog/zones", headers={"If-None-Match": first.headers["ETag"]}
    )
    assert second.status_code == 304
    assert second.content == b""


@pytest.mark.parametrize("path", ["vehicles", "extras", "activities", "packages"])
async def test_catalog_lists(api: AsyncClient, path: str) -> None:
    response = await api.get(f"/api/v1/catalog/{path}")
    assert response.status_code == 200
    assert response.json()


async def test_hotel_page(api: AsyncClient) -> None:
    response = await api.get("/api/v1/catalog/hotels/one-and-only-palmilla")
    assert response.status_code == 200, response.text
    page = response.json()
    assert page["zone"]["slug"]
    assert {rate["trip_type"] for rate in page["rates"]} == {"one_way", "round_trip"}
    assert (await api.get("/api/v1/catalog/hotels/nope")).status_code == 404


async def test_quotes_are_rate_limited(api: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.core.rate_limit.time.time", lambda: 120.0)
    statuses = [(await api.post("/api/v1/quotes", json={})).status_code for _ in range(61)]
    assert set(statuses[:60]) == {422}
    assert statuses[60] == 429


async def test_unconfigured_company_is_unavailable(
    api: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEFAULT_COMPANY_SLUG", "missing")
    get_settings.cache_clear()
    assert (await api.get("/api/v1/catalog/zones")).status_code == 503
