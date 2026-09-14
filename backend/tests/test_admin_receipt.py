from io import BytesIO

from httpx import AsyncClient
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking
from tests.test_admin_booking_actions import _login
from tests.test_admin_bookings import _create

URL = "/api/v1/admin/bookings"


async def _booking_id(db: AsyncSession, code: str) -> str:
    booking_id = await db.scalar(select(Booking.id).where(Booking.code == code))
    assert booking_id is not None
    return str(booking_id)


async def test_receipt_has_selectable_payment_details(api: AsyncClient, db: AsyncSession) -> None:
    created = await _create(api, db)
    headers = await _login(api, db)
    booking_id = await _booking_id(db, created["code"])

    marked = await api.post(
        f"{URL}/{booking_id}/mark-paid",
        json={"provider": "bank_transfer", "reference": "WIRE-4821"},
        headers=headers,
    )
    assert marked.status_code == 200, marked.text
    payment_id = marked.json()["payments"][0]["id"]

    response = await api.get(
        f"{URL}/{booking_id}/payments/{payment_id}/receipt.pdf", headers=headers
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "private, no-store"

    text = "".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
    for expected in (created["code"], "Ana López", "Bank transfer", "WIRE-4821"):
        assert expected in text, expected


async def test_receipt_404s_for_a_payment_of_another_booking(
    api: AsyncClient, db: AsyncSession
) -> None:
    first = await _create(api, db)
    second = await _create(
        api,
        db,
        customer={
            "first_name": "Luis",
            "last_name": "Pérez",
            "email": "luis@example.com",
            "confirm_email": "luis@example.com",
            "phone": "+52 624 000 0000",
        },
    )
    headers = await _login(api, db)

    first_id = await _booking_id(db, first["code"])
    second_id = await _booking_id(db, second["code"])
    marked = (
        await api.post(f"{URL}/{first_id}/mark-paid", json={"provider": "cash"}, headers=headers)
    ).json()
    payment_id = marked["payments"][0]["id"]

    response = await api.get(
        f"{URL}/{second_id}/payments/{payment_id}/receipt.pdf", headers=headers
    )
    assert response.status_code == 404


async def test_receipt_requires_admin_auth(api: AsyncClient, db: AsyncSession) -> None:
    created = await _create(api, db)
    booking_id = await _booking_id(db, created["code"])
    response = await api.get(f"{URL}/{booking_id}/payments/{booking_id}/receipt.pdf")
    assert response.status_code == 401
