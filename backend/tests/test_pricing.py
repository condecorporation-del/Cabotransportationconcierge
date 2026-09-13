import json
from datetime import date, time, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DiscountType, Hotel, ItemType, Promotion, TripType, Zone
from app.schemas.quotes import (
    ActivityQuoteRequest,
    ExtraIn,
    LegIn,
    Quote,
    TransferQuoteRequest,
)
from app.services.pricing import QuoteError, quote_activity, quote_transfer
from scripts.seed_catalog import CATALOG_PATH, seed

CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
RATES = {
    (r["zone"], r["vehicle_class"], r["trip_type"]): r["price_cents"] for r in CATALOG["rates"]
}
TODAY = date(2026, 9, 12)
SEPTEMBER = date(2026, 9, 15)
OCTOBER = date(2026, 10, 15)


@pytest.fixture
async def hotels(db: AsyncSession) -> dict[str, Hotel]:
    """Catálogo real sembrado en la sesión; un hotel por zona."""
    await seed(db, CATALOG)
    rows = await db.execute(
        select(Zone.slug, Hotel).join(Hotel, Hotel.zone_id == Zone.id).order_by(Hotel.name)
    )
    by_zone: dict[str, Hotel] = {}
    for slug, hotel in rows.tuples():
        by_zone.setdefault(slug, hotel)
    assert set(by_zone) == {z["slug"] for z in CATALOG["zones"]}
    return by_zone


def request(
    hotel: Hotel,
    trip: TripType = TripType.ONE_WAY,
    passengers: int = 2,
    when: date = OCTOBER,
    at: time | None = None,
    **extra_fields: object,
) -> TransferQuoteRequest:
    legs = [LegIn(service_date=when, service_time=at)]
    if trip is TripType.ROUND_TRIP:
        legs.append(LegIn(service_date=when + timedelta(days=5)))
    return TransferQuoteRequest.model_validate(
        {"hotel_id": hotel.id, "trip_type": trip, "passengers": passengers, "legs": legs}
        | extra_fields
    )


async def quote(db: AsyncSession, transfer: TransferQuoteRequest) -> Quote:
    return await quote_transfer(db, transfer, TODAY)


@pytest.mark.parametrize("trip", list(TripType))
@pytest.mark.parametrize(("passengers", "vehicle"), [(2, "SUBURBAN"), (8, "SPRINTER")])
async def test_base_rate_matches_catalog_in_every_zone(
    db: AsyncSession, hotels: dict[str, Hotel], trip: TripType, passengers: int, vehicle: str
) -> None:
    for zone, hotel in hotels.items():
        result = await quote(db, request(hotel, trip, passengers))
        assert (result.zone, result.vehicle_class) == (zone, vehicle)
        assert result.total_cents == result.subtotal_cents == RATES[(zone, vehicle, trip.value)]


@pytest.mark.parametrize(
    ("passengers", "vehicle"), [(1, "SUBURBAN"), (5, "SUBURBAN"), (6, "SPRINTER"), (14, "SPRINTER")]
)
async def test_vehicle_is_chosen_by_passengers(
    db: AsyncSession, hotels: dict[str, Hotel], passengers: int, vehicle: str
) -> None:
    result = await quote(db, request(hotels["cabo-san-lucas"], passengers=passengers))
    assert result.vehicle_class == vehicle


async def test_vehicle_limits(db: AsyncSession, hotels: dict[str, Hotel]) -> None:
    hotel = hotels["cabo-san-lucas"]
    with pytest.raises(QuoteError) as too_many:
        await quote(db, request(hotel, passengers=15))
    assert too_many.value.code == "too_many_passengers"

    upgrade = await quote(db, request(hotel, passengers=2, vehicle_class="SPRINTER"))
    assert upgrade.total_cents == RATES[("cabo-san-lucas", "SPRINTER", "one_way")]

    with pytest.raises(QuoteError) as too_small:
        await quote(db, request(hotel, passengers=7, vehicle_class="SUBURBAN"))
    assert too_small.value.code == "vehicle_too_small"


async def test_extras_are_priced_by_quantity_within_limits(
    db: AsyncSession, hotels: dict[str, Hotel]
) -> None:
    hotel = hotels["cabo-san-lucas"]
    base = RATES[("cabo-san-lucas", "SUBURBAN", "one_way")]

    result = await quote(db, request(hotel, extras=[ExtraIn(code="BABY_SEAT", quantity=2)]))
    assert result.total_cents == base + 2 * 1500

    for code, quantity, error in [
        ("BABY_SEAT", 3, "extra_quantity"),
        ("NIGHT_SURCHARGE", 1, "extra_unavailable"),
        ("INCLUDED_BASIC_KIT", 1, "extra_unavailable"),
        ("NOT_A_REAL_EXTRA", 1, "extra_unavailable"),
    ]:
        with pytest.raises(QuoteError) as rejected:
            await quote(db, request(hotel, extras=[ExtraIn(code=code, quantity=quantity)]))
        assert rejected.value.code == error


@pytest.mark.parametrize(
    ("at", "charged"),
    [
        (time(23, 0), True),
        (time(4, 59), True),
        (time(5, 0), False),
        (time(22, 59), False),
        (None, False),
    ],
)
async def test_night_surcharge_follows_company_window(
    db: AsyncSession, hotels: dict[str, Hotel], at: time | None, charged: bool
) -> None:
    result = await quote(db, request(hotels["san-jose-del-cabo"], at=at))
    assert any(line.code == "NIGHT_SURCHARGE" for line in result.lines) is charged


async def test_september_promo_discounts_only_the_transfer_base(
    db: AsyncSession, hotels: dict[str, Hotel]
) -> None:
    hotel = hotels["cabo-san-lucas"]
    extras = [ExtraIn(code="BABY_SEAT", quantity=1)]

    september = await quote(db, request(hotel, when=SEPTEMBER, extras=extras))
    assert september.subtotal_cents == 11000 + 1500
    assert september.discount_cents == 1100
    assert september.total_cents == 11400
    assert september.lines[-1].kind is ItemType.DISCOUNT

    october = await quote(db, request(hotel, when=OCTOBER, extras=extras))
    assert october.discount_cents == 0
    assert october.promotion is None


async def test_promo_code_ignores_case_and_only_the_best_promotion_applies(
    db: AsyncSession, hotels: dict[str, Hotel]
) -> None:
    db.add(
        Promotion(code="VIP20", name={"en": "VIP"}, discount_type=DiscountType.FIXED, value=2000)
    )
    await db.flush()
    hotel = hotels["cabo-san-lucas"]

    result = await quote(db, request(hotel, when=SEPTEMBER, promo_code="vip20"))

    assert result.discount_cents == 2000
    assert [line.kind for line in result.lines].count(ItemType.DISCOUNT) == 1
    with pytest.raises(QuoteError) as invalid:
        await quote(db, request(hotel, promo_code="NOPE"))
    assert invalid.value.code == "invalid_promo_code"


async def test_activity_combo_price_per_guest_with_park_fee_on_site(
    db: AsyncSession, hotels: dict[str, Hotel]
) -> None:
    def combo(activities: list[str]) -> ActivityQuoteRequest:
        return ActivityQuoteRequest(
            package="crazy-combo-3", activities=activities, guests=2, service_date=OCTOBER
        )

    result = await quote_activity(db, combo(["atv", "camel-ride", "sky-bikes"]))
    assert result.total_cents == 2 * 12500
    assert result.due_on_site_cents == 2 * 2500

    for activities, error in [
        (["atv", "camel-ride"], "activity_count"),
        (["atv", "atv", "camel-ride"], "duplicate_activities"),
        (["atv", "camel-ride", "swimming-with-sharks"], "activity_not_found"),
    ]:
        with pytest.raises(QuoteError) as rejected:
            await quote_activity(db, combo(activities))
        assert rejected.value.code == error


def test_request_validation_rejects_inconsistent_trips() -> None:
    base = {"hotel_id": "8b0c1c6e-0000-4000-8000-000000000000", "passengers": 2}
    one_leg = [{"service_date": "2026-10-15"}]
    backwards = [{"service_date": "2026-10-15"}, {"service_date": "2026-10-10"}]
    for payload in (
        base | {"trip_type": "round_trip", "legs": one_leg},
        base | {"trip_type": "round_trip", "legs": backwards},
        base | {"trip_type": "one_way", "legs": one_leg, "price_cents": 1},
    ):
        with pytest.raises(ValidationError):
            TransferQuoteRequest.model_validate(payload)
