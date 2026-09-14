"""Recibo PDF de un pago manual (F4.8): mismo estilo que el voucher (F3.8), mucho más corto.

Solo para pagos manuales (efectivo, transferencia, cuenta): un pago de Stripe ya tiene su
propio recibo, el que envía Stripe.
"""

from fpdf import FPDF

from app.models import Booking, Company, Customer, Payment
from app.services.voucher import GOLD, INK, LOGO, MUTED, latin1, money

TEXT = {
    "en": {
        "title": "Payment receipt",
        "code": "Booking code",
        "guest": "Guest",
        "method": "Method",
        "amount": "Amount received",
        "reference": "Reference",
        "date": "Date",
    },
    "es": {
        "title": "Recibo de pago",
        "code": "Código de reserva",
        "guest": "Huésped",
        "method": "Método",
        "amount": "Monto recibido",
        "reference": "Referencia",
        "date": "Fecha",
    },
}

METHOD_LABEL = {
    "en": {
        "cash": "Cash",
        "bank_transfer": "Bank transfer",
        "manual": "Manual",
        "account": "Account",
    },
    "es": {
        "cash": "Efectivo",
        "bank_transfer": "Transferencia",
        "manual": "Manual",
        "account": "Cuenta",
    },
}


def render_receipt(
    payment: Payment, booking: Booking, customer: Customer, company: Company
) -> bytes:
    t = TEXT.get(booking.language, TEXT["en"])
    method = METHOD_LABEL.get(booking.language, METHOD_LABEL["en"]).get(
        payment.provider.value, payment.provider.value
    )

    pdf = FPDF(format="letter")
    pdf.set_title(f"{company.name} {booking.code} receipt")
    pdf.add_page()

    pdf.image(str(LOGO), x=9, y=7, w=21)
    pdf.set_xy(32, 11)
    pdf.set_font("helvetica", "B", 15)
    pdf.set_text_color(*GOLD)
    pdf.cell(text=latin1(company.name.upper()))
    pdf.set_xy(32, 19)
    pdf.set_font("helvetica", "", 10)
    pdf.set_text_color(*MUTED)
    pdf.cell(text=latin1(t["title"]))

    def field(label: str, value: str) -> None:
        pdf.set_font("helvetica", "", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(38, 6, latin1(label))
        pdf.set_font("helvetica", "B", 10)
        pdf.set_text_color(*INK)
        pdf.multi_cell(0, 6, latin1(value), new_x="LMARGIN", new_y="NEXT")

    pdf.set_y(44)
    field(t["code"], booking.code)
    field(t["guest"], customer.name)
    field(t["method"], method)
    field(t["amount"], money(payment.amount_cents, payment.currency))
    if payment.reference:
        field(t["reference"], payment.reference)
    if payment.paid_at:
        field(t["date"], f"{payment.paid_at:%Y-%m-%d %H:%M}")
    return bytes(pdf.output())
