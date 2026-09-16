"""Plantillas de correo (F5.3): bilingües para el cliente, en inglés para el equipo de CTC
y para los choferes (F5.9).

Sin motor de plantillas (Jinja o MJML): son trece correos cortos, f-strings alcanza y no
agrega una dependencia. Cada función recibe el `context` que armó quien encoló (F5.2) y
devuelve `(asunto, html, texto plano)`.
"""

from collections.abc import Callable
from typing import Any

GOLD = "#A9823F"
INK = "#0C0F14"
Render = Callable[[dict[str, Any], str], tuple[str, str, str]]


def _shell(language: str, title: str, lines: list[str], cta: tuple[str, str] | None = None) -> str:
    paragraphs = "".join(f'<p style="margin:0 0 16px;line-height:1.6">{line}</p>' for line in lines)
    button = ""
    if cta:
        label, url = cta
        button = (
            f'<p style="margin:24px 0"><a href="{url}" '
            f'style="background:{GOLD};color:{INK};padding:12px 24px;text-decoration:none;'
            f'font-weight:700;border-radius:2px;display:inline-block">{label}</a></p>'
        )
    return (
        f'<!doctype html><html lang="{language}"><body style="margin:0;background:#F4F1EA;'
        f'font-family:Georgia,serif;color:{INK}"><div style="max-width:520px;margin:0 auto;'
        f'padding:32px 24px">'
        f'<p style="color:{GOLD};font-weight:700;letter-spacing:.08em;font-size:13px;'
        f'margin:0 0 24px">CABO TRANSPORTATION CONCIERGE</p>'
        f'<h1 style="font-size:20px;margin:0 0 16px">{title}</h1>{paragraphs}{button}'
        f"</div></body></html>"
    )


def _text(title: str, lines: list[str], cta: tuple[str, str] | None = None) -> str:
    body = "\n\n".join([title, *lines])
    return f"{body}\n\n{cta[1]}" if cta else body


def _pending_payment(context: dict[str, Any], language: str) -> tuple[str, str, str]:
    code, url = context["code"], context["manage_url"]
    if language == "es":
        subject, title = f"Completa tu reserva {code}", "Falta un paso para tu traslado"
        lines = [
            f"Tu código de reserva es <strong>{code}</strong>.",
            "Termina el pago para confirmarla.",
        ]
        cta = ("Completar el pago", url)
    else:
        subject, title = f"Complete your booking {code}", "One step left for your transfer"
        lines = [
            f"Your booking code is <strong>{code}</strong>.",
            "Finish the payment to confirm it.",
        ]
        cta = ("Complete your payment", url)
    return subject, _shell(language, title, lines, cta), _text(title, lines, cta)


def _confirmed(context: dict[str, Any], language: str) -> tuple[str, str, str]:
    code, manage_url, voucher_url = context["code"], context["manage_url"], context["voucher_url"]
    balance = context.get("balance_note")
    if language == "es":
        subject, title = f"Tu reserva {code} está confirmada", "¡Nos vemos en Los Cabos!"
        lines = [f"La reserva <strong>{code}</strong> quedó confirmada.", "Tu voucher está listo."]
        if balance:
            lines.append(balance)
        lines.append(f'<a href="{manage_url}">Ver o cambiar tu reserva</a>.')
        cta = ("Descargar el voucher", voucher_url)
    else:
        subject, title = f"Your booking {code} is confirmed", "See you in Los Cabos!"
        lines = [f"Booking <strong>{code}</strong> is confirmed.", "Your voucher is ready."]
        if balance:
            lines.append(balance)
        lines.append(f'<a href="{manage_url}">View or change your booking</a>.')
        cta = ("Download your voucher", voucher_url)
    return subject, _shell(language, title, lines, cta), _text(title, lines, cta)


def _changed(context: dict[str, Any], language: str) -> tuple[str, str, str]:
    code, url = context["code"], context["manage_url"]
    if language == "es":
        subject, title = f"Actualizamos tu reserva {code}", "Tu reserva cambió"
        lines = [f"Hicimos el cambio que pediste en <strong>{code}</strong>."]
        cta = ("Ver los detalles", url)
    else:
        subject, title = f"Your booking {code} was updated", "Your booking changed"
        lines = [f"We made the change you asked for on <strong>{code}</strong>."]
        cta = ("View the details", url)
    return subject, _shell(language, title, lines, cta), _text(title, lines, cta)


def _cancelled(context: dict[str, Any], language: str) -> tuple[str, str, str]:
    code = context["code"]
    if language == "es":
        subject, title = f"Cancelamos tu reserva {code}", "Reserva cancelada"
        lines = [
            f"La reserva <strong>{code}</strong> quedó cancelada.",
            "Escríbenos si fue un error.",
        ]
    else:
        subject, title = f"Your booking {code} was cancelled", "Booking cancelled"
        lines = [
            f"Booking <strong>{code}</strong> is now cancelled.",
            "Reach out if this was a mistake.",
        ]
    return subject, _shell(language, title, lines), _text(title, lines)


def _contact_ack(context: dict[str, Any], language: str) -> tuple[str, str, str]:
    name = context["name"]
    if language == "es":
        subject, title = "Recibimos tu mensaje", f"Gracias, {name}"
        lines = ["Nuestro equipo te responde en menos de un día hábil."]
    else:
        subject, title = "We received your message", f"Thank you, {name}"
        lines = ["Our team will reply within one business day."]
    return subject, _shell(language, title, lines), _text(title, lines)


def _booking_new(context: dict[str, Any], _language: str) -> tuple[str, str, str]:
    code = context["code"]
    title = f"New {context['payment_method']} booking {code}"
    lines = [
        f"Customer: {context['customer_name']}",
        f"Total: {context['total_display']}",
    ]
    return title, _shell("en", title, lines), _text(title, lines)


def _booking_paid_ops(context: dict[str, Any], _language: str) -> tuple[str, str, str]:
    title = f"Booking {context['code']} is now {context['status']}"
    lines = ["Full detail is in the admin."]
    return title, _shell("en", title, lines), _text(title, lines)


def _booking_changed_ops(context: dict[str, Any], _language: str) -> tuple[str, str, str]:
    title = f"Customer changed booking {context['code']}"
    return title, _shell("en", title, [title]), title


def _booking_cancelled_ops(context: dict[str, Any], _language: str) -> tuple[str, str, str]:
    title = f"Booking {context['code']} was cancelled"
    lines = [context["reason"]] if context.get("reason") else [title]
    return title, _shell("en", title, lines), _text(title, lines)


def _contact_lead(context: dict[str, Any], _language: str) -> tuple[str, str, str]:
    title = f"New message from {context['name']}"
    lines = [context["message"], f"Reply to: {context['email']}"]
    return title, _shell("en", title, lines), _text(title, lines)


def _driver_assigned(context: dict[str, Any], _language: str) -> tuple[str, str, str]:
    title = f"You're assigned: {context['code']} on {context['service_date']}"
    lines = [
        f"Pickup: {context['pickup_time'] or 'TBD'} at {context['origin']}",
        f"Drop-off: {context['destination']}",
        f"Passengers: {context['pax']}",
    ]
    return title, _shell("en", title, lines), _text(title, lines)


def _reminder(context: dict[str, Any], language: str) -> tuple[str, str, str]:
    code, manage_url = context["code"], context["manage_url"]
    crew = context.get("crew")
    if language == "es":
        subject, title = f"Tu traslado es mañana — reserva {code}", "Mañana te recogemos"
        lines = [
            f"Reserva <strong>{code}</strong>, {context['service_date']}.",
            f"Te recogemos a las {context['pickup_time'] or 'la hora acordada'} "
            f"en {context['origin']}.",
            f"Destino: {context['destination']}.",
        ]
        lines.append(crew or "Te confirmamos chofer y vehículo antes de la recogida.")
        cta = ("Ver tu reserva", manage_url)
    else:
        subject, title = f"Your transfer is tomorrow — booking {code}", "We pick you up tomorrow"
        lines = [
            f"Booking <strong>{code}</strong>, {context['service_date']}.",
            f"Pickup at {context['pickup_time'] or 'the agreed time'} from {context['origin']}.",
            f"Drop-off: {context['destination']}.",
        ]
        lines.append(crew or "We will confirm your driver and vehicle before pickup.")
        cta = ("View your booking", manage_url)
    return subject, _shell(language, title, lines, cta), _text(title, lines, cta)


def _review_request(context: dict[str, Any], language: str) -> tuple[str, str, str]:
    review_url = context["review_url"]
    if language == "es":
        subject, title = "¿Cómo estuvo tu viaje?", "Gracias por viajar con nosotros"
        lines = [
            f"Esperamos que tu traslado de la reserva <strong>{context['code']}</strong> "
            f"haya salido perfecto.",
            "Si tienes dos minutos, una reseña nos ayuda muchísimo.",
        ]
        cta = ("Dejar una reseña", review_url)
    else:
        subject, title = "How was your ride?", "Thank you for riding with us"
        lines = [
            f"We hope your transfer on booking <strong>{context['code']}</strong> went perfectly.",
            "If you have two minutes, a review helps us a lot.",
        ]
        cta = ("Leave a review", review_url)
    return subject, _shell(language, title, lines, cta), _text(title, lines, cta)


TEMPLATES: dict[str, Render] = {
    "booking_pending_payment": _pending_payment,
    "booking_confirmed": _confirmed,
    "booking_changed": _changed,
    "booking_cancelled": _cancelled,
    "contact_ack": _contact_ack,
    "booking_new": _booking_new,
    "booking_paid_ops": _booking_paid_ops,
    "booking_changed_ops": _booking_changed_ops,
    "booking_cancelled_ops": _booking_cancelled_ops,
    "contact_lead": _contact_lead,
    "driver_assigned": _driver_assigned,
    "booking_reminder": _reminder,
    "review_request": _review_request,
}


def render(template: str, language: str, context: dict[str, Any]) -> tuple[str, str, str]:
    return TEMPLATES[template](context, language)
