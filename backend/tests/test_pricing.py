import json
from datetime import date, time, timedelta

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DiscountType, Hotel, ItemType, Promotion, ServiceScope, TripType, Zone
from app.schemas.quotes import (
    ActivityQuoteRequest,
    ExtraIn,
    LegIn,
    Quote,
    TransferQuoteRequest,
)
from app.services.pricing import QuoteError, night_hours, quote_activity, quote_transfer
from scripts.seed_catalog import CATALOG_PATH, seed

CATALOG = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
RATES = {
    (r["zone"], r["vehicle_class"], r["trip_type"], r["service_scope"]): r["price_cents"]
    for r in CATALOG["rates"]
}
TODAY = date(2026, 9, 12)
SEPTEMBER = date(2026, 9, 15)
OCTOBER = date(2026, 10, 15)
CSL = "cabo-san-lucas-marina"
SJC = "san-jose-del-cabo-estuary"


@pytest.fixture
async def hotels(db: AsyncSession) -> dict[str, Hotel]:
    """Catálogo real sembrado en la sesión; un hotel por zona que tenga hoteles."""
    await seed(db, CATALOG)
    rows = await db.execute(
        select(Zone.slug, Hotel).join(Hotel, Hotel.zone_id == Zone.id).order_by(Hotel.name)
    )
    by_zone: dict[str, Hotel] = {}
    for slug, hotel in rows.tuples():
        by_zone.setdefault(slug, hotel)
    assert set(by_zone) == {h["zone"] for h in CATALOG["hotels"]}
    return by_zone


def request(
    hotel: Hotel,
    trip: TripType = TripType.ONE_WAY,
    passengers: int = 2,
    when: date = OCTOBER,
    at: time | None = None,
    back_at: time | None = None,
    **fields: object,
) -> TransferQuoteRequest:
    legs = [LegIn(service_date=when, service_time=at)]
    if trip is TripType.ROUND_TRIP:
        legs.append(LegIn(service_date=when + timedelta(days=5), service_time=back_at))
    return TransferQuoteRequest.model_validate(
        {
            "hotel_id": hotel.id,
            "trip_type": trip,
            "passengers": passengers,
            "legs": legs,
            "payment": "cash",
        }
        | fields
    )


async def quote(db: AsyncSession, transfer: TransferQuoteRequest) -> Quote:
    return await quote_transfer(db, transfer, TODAY)


@pytest.mark.parametrize("scope", list(ServiceScope))
@pytest.mark.parametrize("trip", list(TripType))
async def test_every_rate_matches_the_catalog(
    db: AsyncSession, hotels: dict[str, Hotel], trip: TripType, scope: ServiceScope
) -> None:
    for zone, hotel in hotels.items():
        for vehicle in CATALOG["vehicle_classes"]:
            key = (zone, vehicle["code"], trip.value, scope.value)
            transfer = request(hotel, trip, vehicle_class=vehicle["code"], service_scope=scope)
            if key not in RATES:
                with pytest.raises(QuoteError) as missing:
                    await quote(db, transfer)
                assert missing.value.code == "rate_unavailable"
                continue
            result = await quote(db, transfer)
            assert (result.zone, result.vehicle_count) == (zone, 1)
            assert result.total_cents == RATES[key], key


@pytest.mark.parametrize(
    ("passengers", "vehicle", "units"),
    [(2, "SUBURBAN", 1), (8, "VAN", 1), (12, "SPRINTER", 1), (20, "VAN", 2)],
)
async def test_any_vehicle_takes_the_lowest_total(
    db: AsyncSession, hotels: dict[str, Hotel], passengers: int, vehicle: str, units: int
) -> None:
    result = await quote(db, request(hotels[CSL], passengers=passengers))
    assert (result.vehicle_class, result.vehicle_count) == (vehicle, units)
    assert result.total_cents == RATES[(CSL, vehicle, "one_way", "airport")] * units


async def test_groups_that_do_not_fit_get_more_units(
    db: AsyncSession, hotels: dict[str, Hotel]
) -> None:
    result = await quote(db, request(hotels[CSL], passengers=8, vehicle_class="SUBURBAN"))
    assert (result.vehicle_count, result.total_cents) == (2, 2 * 11000)
    assert result.lines[0].quantity == 2

    with pytest.raises(ValidationError):
        request(hotels[CSL], passengers=21)


@pytest.mark.parametrize(
    ("trip", "total"), [(TripType.ONE_WAY, 26000), (TripType.ROUND_TRIP, 50500)]
)
async def test_limousine_charges_passengers_after_six_on_each_leg(
    db: AsyncSession, hotels: dict[str, Hotel], trip: TripType, total: int
) -> None:
    result = await quote(db, request(hotels[CSL], trip, passengers=8, vehicle_class="LIMOUSINE"))
    extra = next(line for line in result.lines if line.code == "EXTRA_PASSENGERS")
    assert extra.unit_price_cents == 1000
    assert result.total_cents == total


async def test_extras_with_free_units_vehicle_prices_and_one_per_vehicle(
    db: AsyncSession, hotels: dict[str, Hotel]
) -> None:
    hotel = hotels[CSL]
    seats = await quote(db, request(hotel, extras=[ExtraIn(code="CAR_SEAT", quantity=2)]))
    assert seats.total_cents == 11000 + 1000
    assert [line.unit_price_cents for line in seats.lines if line.code == "CAR_SEAT"] == [0, 1000]

    shopping = [ExtraIn(code="SHOPPING_STOP", quantity=1)]
    escalade = await quote(db, request(hotel, vehicle_class="ESCALADE", extras=shopping))
    assert escalade.total_cents == 16500 + 12000

    with pytest.raises(QuoteError) as per_vehicle:
        await quote(db, request(hotel, passengers=8, vehicle_class="SUBURBAN", extras=shopping))
    assert per_vehicle.value.code == "extra_per_vehicle"
    two_stops = [ExtraIn(code="SHOPPING_STOP", quantity=2)]
    both = await quote(db, request(hotel, passengers=8, vehicle_class="SUBURBAN", extras=two_stops))
    assert both.total_cents == 2 * 11000 + 2 * 5000

    for code, quantity, error in [
        ("CAR_SEAT", 5, "extra_quantity"),
        ("NIGHT_SURCHARGE", 1, "extra_unavailable"),
        ("INCLUDED_BASIC_KIT", 1, "extra_unavailable"),
        ("NOT_A_REAL_EXTRA", 1, "extra_unavailable"),
    ]:
        with pytest.raises(QuoteError) as rejected:
            await quote(db, request(hotel, extras=[ExtraIn(code=code, quantity=quantity)]))
        assert rejected.value.code == error


@pytest.mark.parametrize(
    ("at", "hours"),
    [
        (time(23, 0), 1),
        (time(0, 14), 1),
        (time(0, 15), 2),
        (time(4, 59), 6),
        (time(5, 0), 0),
        (time(22, 59), 0),
        (None, 0),
    ],
)
def test_night_hours_follow_the_reference(at: time | None, hours: int) -> None:
    assert night_hours(at, time(23, 0), time(5, 0)) == hours


async def test_night_surcharge_is_hours_times_the_vehicle_rate(
    db: AsyncSession, hotels: dict[str, Hotel]
) -> None:
    hotel = hotels[SJC]
    one_way = await quote(db, request(hotel, at=time(23, 30)))
    assert one_way.total_cents == 9000 + 8500
    round_trip = await quote(
        db, request(hotel, TripType.ROUND_TRIP, at=time(23, 30), back_at=time(0, 30))
    )
    assert round_trip.total_cents == 16000 + 3 * 8500
    escalade = await quote(db, request(hotel, at=time(23, 30), vehicle_class="ESCALADE"))
    assert escalade.total_cents == 14500 + 15000
    day = await quote(db, request(hotel, at=time(14, 0)))
    assert all(line.code != "NIGHT_SURCHARGE" for line in day.lines)


async def test_september_promo_discounts_the_base_of_every_unit(
    db: AsyncSession, hotels: dict[str, Hotel]
) -> None:
    hotel = hotels[CSL]
    seats = [ExtraIn(code="CAR_SEAT", quantity=2)]

    september = await quote(db, request(hotel, when=SEPTEMBER, extras=seats))
    assert (september.subtotal_cents, september.discount_cents) == (12000, 1100)
    assert september.total_cents == 10900
    assert september.lines[-1].kind is ItemType.DISCOUNT

    group = await quote(db, request(hotel, when=SEPTEMBER, passengers=8, vehicle_class="SUBURBAN"))
    assert group.discount_cents == 2200

    october = await quote(db, request(hotel, when=OCTOBER, extras=seats))
    assert (october.discount_cents, october.promotion) == (0, None)


async def test_card_adds_tax_and_cash_asks_for_a_deposit_on_premium_vehicles(
    db: AsyncSession, hotels: dict[str, Hotel]
) -> None:
    hotel = hotels[CSL]
    card = await quote(db, request(hotel, payment="card"))
    assert (card.subtotal_cents, card.tax_cents, card.total_cents) == (11000, 1760, 12760)

    departure = request(hotel, payment="card", direction="departure")
    assert (await quote(db, departure)).tax_cents == 0
    with pytest.raises(QuoteError) as no_cash:
        await quote(db, request(hotel, direction="departure"))
    assert no_cash.value.code == "cash_unavailable"

    for vehicle, deposit in [("SUBURBAN", 0), ("ESCALADE", 10000), ("LIMOUSINE", 11000)]:
        cash = await quote(db, request(hotel, vehicle_class=vehicle))
        assert (cash.tax_cents, cash.deposit_cents) == (0, deposit), vehicle


async def test_promo_code_ignores_case_and_only_the_best_promotion_applies(
    db: AsyncSession, hotels: dict[str, Hotel]
) -> None:
    db.add(
        Promotion(code="VIP20", name={"en": "VIP"}, discount_type=DiscountType.FIXED, value=2000)
    )
    await db.flush()
    hotel = hotels[CSL]

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
