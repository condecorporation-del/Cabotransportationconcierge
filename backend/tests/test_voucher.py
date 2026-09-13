from io import BytesIO

from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy.ext.asyncio import AsyncSession

from tests.test_booking_access import _bearer, _book
from tests.test_bookings import URL


async def test_voucher_has_selectable_booking_details(api: AsyncClient, db: AsyncSession) -> None:
    created = await _book(api, db)
    url = f"{URL}/{created['code']}/voucher.pdf"
    response = await api.get(url, headers=_bearer(created["token"]))
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"

    text = "".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
    for expected in (
        created["code"],
        "Ana López",
        "One and Only Palmilla",
        "AA1245",
        "Meeting point",
    ):
        assert expected in text, expected


async def test_voucher_needs_the_token_of_its_booking(api: AsyncClient, db: AsyncSession) -> None:
    first = await _book(api, db)
    second = await _book(api, db, email="luis@example.com")
    url = f"{URL}/{second['code']}/voucher.pdf"
    assert (await api.get(url)).status_code == 401
    assert (await api.get(url, headers=_bearer(first["token"]))).status_code == 404
