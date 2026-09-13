"""Voucher PDF (F3.8): texto seleccionable, tramos, punto de encuentro y QR del código.

fpdf2 + segno en Python puro: sin GTK/Pango del sistema, igual en Windows y en Railway.
"""

from pathlib import Path

import segno
from fpdf import FPDF

from app.models import Booking, Company, CompanySettings, Customer, LegType

GOLD = (169, 130, 63)
INK = (24, 24, 27)
MUTED = (113, 113, 122)
# Medallón oficial de Cabo Transportation Concierge (WORKPLAN §3.5.6).
LOGO = Path(__file__).resolve().parents[1] / "assets" / "ctc-medallion-192.png"
TEXT = {
    "en": {
        "title": "Booking voucher",
        "code": "Booking code",
        "guest": "Guest",
        "status": "Status",
        "arrival": "Arrival",
        "departure": "Departure",
        "local": "Transfer",
        "pickup": "Pickup",
        "route": "Route",
        "flight": "Flight",
        "passengers": "Passengers",
        "summary": "Summary",
        "total": "Total",
        "meeting": "Meeting point",
        "meeting_default": "Your meeting point instructions are in your confirmation email.",
        "contact": "Questions",
        "cash_balance": "Balance payable in cash on arrival",
    },
    "es": {
        "title": "Voucher de reserva",
        "code": "Código de reserva",
        "guest": "Huésped",
        "status": "Estado",
        "arrival": "Llegada",
        "departure": "Salida",
        "local": "Traslado",
        "pickup": "Pickup",
        "route": "Ruta",
        "flight": "Vuelo",
        "passengers": "Pasajeros",
        "summary": "Resumen",
        "total": "Total",
        "meeting": "Punto de encuentro",
        "meeting_default": "Las instrucciones del punto de encuentro están en tu correo.",
        "contact": "Dudas",
        "pending_payment": "Pendiente de pago",
        "offline_hold": "Por confirmar",
        "confirmed": "Confirmada",
        "paid": "Pagada",
        "completed": "Completada",
        "cancelled": "Cancelada",
        "cash_balance": "Saldo a pagar en efectivo a la llegada",
    },
}


def _latin1(text: str) -> str:
    """Las fuentes base del PDF cubren latin-1 (acentos y ñ incluidos)."""
    return text.encode("latin-1", "replace").decode("latin-1")


def _money(cents: int, currency: str) -> str:
    sign = "-" if cents < 0 else ""
    return f"{sign}${abs(cents) // 100:,}.{abs(cents) % 100:02d} {currency}"


def render_voucher(
    booking: Booking, customer: Customer, company: Company, settings: CompanySettings
) -> bytes:
    t = TEXT.get(booking.language, TEXT["en"])
    pdf = FPDF(format="letter")
    pdf.set_title(f"{company.name} {booking.code}")
    pdf.add_page()

    pdf.image(str(LOGO), x=9, y=7, w=21)
    pdf.set_xy(32, 11)
    pdf.set_font("helvetica", "B", 15)
    pdf.set_text_color(*GOLD)
    pdf.cell(text=_latin1(company.name.upper()))
    pdf.set_xy(32, 19)
    pdf.set_font("helvetica", "", 10)
    pdf.set_text_color(*MUTED)
    pdf.cell(text=_latin1(t["title"]))

    matrix = segno.make(booking.code, error="m").matrix
    module = 28 / len(matrix)
    pdf.set_fill_color(*INK)
    for y, row in enumerate(matrix):
        for x, dark in enumerate(row):
            if dark:
                pdf.rect(176 + x * module, 10 + y * module, module, module, style="F")

    def heading(text: str) -> None:
        pdf.ln(5)
        pdf.set_font("helvetica", "B", 12)
        pdf.set_text_color(*GOLD)
        pdf.cell(0, 8, _latin1(text), new_x="LMARGIN", new_y="NEXT")

    def field(label: str, value: str) -> None:
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(38, 6, _latin1(label))
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(*INK)
        pdf.multi_cell(0, 6, _latin1(value), new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(44)
    field(t["code"], booking.code)
    field(t["guest"], customer.name)
    status = booking.status.value
    field(t["status"], t.get(status) or status.replace("_", " ").capitalize())

    for leg in booking.legs:
        heading(t[leg.leg_type.value])
        when = f"{leg.service_date:%Y-%m-%d}" + (
            f"  {leg.pickup_time:%H:%M}" if leg.pickup_time else ""
        )
        field(t["pickup"], when)
        field(t["route"], f"{leg.origin}  >  {leg.destination}")
        if leg.flight_number:
            flight_time = f"{leg.service_time:%H:%M}" if leg.service_time else ""
            field(
                t["flight"], " ".join(filter(None, [leg.airline, leg.flight_number, flight_time]))
            )
        field(t["passengers"], str(leg.pax_adults + leg.pax_children))

    heading(t["summary"])
    for item in booking.items:
        day = f"{item.service_date:%Y-%m-%d}  " if item.service_date else ""
        field(
            _money(item.total_cents, booking.currency), f"{day}{item.description} x{item.quantity}"
        )
    field(t["total"], _money(booking.total_cents, booking.currency))
    if booking.payment_method == "cash":
        field(t["cash_balance"], _money(booking.total_cents, booking.currency))

    if any(leg.leg_type is LegType.ARRIVAL for leg in booking.legs):
        instructions = settings.arrival_instructions
        heading(t["meeting"])
        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(*INK)
        text = instructions.get(booking.language) or instructions.get("en") or t["meeting_default"]
        pdf.multi_cell(0, 5, _latin1(str(text)), new_x="LMARGIN", new_y="NEXT")

    contact = " / ".join(filter(None, [settings.whatsapp or settings.phone, settings.email_ops]))
    if contact:
        heading(t["contact"])
        field("", contact)
    return bytes(pdf.output())
