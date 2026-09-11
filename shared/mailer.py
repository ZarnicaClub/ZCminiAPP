"""Отправка email-уведомлений (подтверждение брони) через SMTP.

Самодостаточный модуль: HTML-шаблон и hero-картинка лежат рядом в shared/email/.
Использует только stdlib (smtplib, email.mime, ssl) — новых зависимостей нет.

Правила безопасности:
- feature-флаг: если SMTP_HOST не задан — ничего не отправляем (только лог);
- рендер и отправка вынесены сюда, БД здесь не трогаем (идемпотентность — в caller);
- ошибка SMTP бросается наружу, чтобы caller зафиксировал её в логе статусов.
"""
import json
import logging
import os
import smtplib
import ssl
from datetime import datetime
from email.header import Header
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from shared.contracts import OrderIn

log = logging.getLogger("shared.mailer")

_EMAIL_DIR = Path(__file__).resolve().parent / "email"
HTML_PATH = _EMAIL_DIR / "email.html"
HERO_PATH = _EMAIL_DIR / "hero.png"

# Русские названия месяцев в родительном падеже (для блока «дата мероприятия»).
_MONTHS_GENITIVE = {
    1: "ЯНВАРЯ", 2: "ФЕВРАЛЯ", 3: "МАРТА", 4: "АПРЕЛЯ",
    5: "МАЯ", 6: "ИЮНЯ", 7: "ИЮЛЯ", 8: "АВГУСТА",
    9: "СЕНТЯБРЯ", 10: "ОКТЯБРЯ", 11: "НОЯБРЯ", 12: "ДЕКАБРЯ",
}

# ---------------------------------------------------------------------
# Константы письма и клуба. Правятся ЗДЕСЬ (в коде), НЕ в окружении.
# В окружении остаются только секреты SMTP: SMTP_HOST/PORT/USER/PASSWORD.
# ---------------------------------------------------------------------
FROM_NAME = "ЗарницаКлаб"
FROM_EMAIL = ""  # пусто = отправитель равен SMTP_USER (почтовый ящик)
EMAIL_SUBJECT = "ЗарницаКлаб — бронирование подтверждено"
EMAIL_FORMAT = "Пейнтбол"
CLUB_MAP_URL = "https://yandex.ru/maps/-/CTXRbV3W"
CLUB_PHONE = "+7 (495) 212-12-23"                      # TODO: реальный телефон клуба
CLUB_MESSENGER = "Telegram / WhatsApp"  # TODO: актуальный ник/ссылка
CLUB_SITE = "ЗарницаКлаб.рф"
CLUB_ADDRESS = "МО, Новая Рига 30км, ЦКАД"                    # TODO: реальный адрес клуба


def is_paid(order: OrderIn) -> bool:
    """Заказ считается оплаченным, если status == 'paid' (конвенция CRM)."""
    return str(order.order_status or "").strip().lower() == "paid"


def _money(value) -> str:
    """Форматирует сумму: 5000 -> '5 000'; 5000.5 -> '5 000.50'."""
    if value in (None, ""):
        return "0"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return str(value)
    if num == int(num):
        return f"{int(num):,}".replace(",", " ")
    return f"{num:,.2f}".replace(",", " ")


def _split_date(order_date) -> tuple[str, str, str]:
    """ISO YYYY-MM-DD -> (day, month_genitive, year)."""
    if not order_date:
        return "", "", ""
    try:
        d = datetime.strptime(str(order_date)[:10], "%Y-%m-%d")
    except ValueError:
        return "", "", ""
    return str(d.day), _MONTHS_GENITIVE.get(d.month, ""), str(d.year)


def _first_product(order: OrderIn) -> tuple[str, str]:
    """(quantity, price) первой позиции из raw_payload payment.products.

    Таблица order_items удалена, поэтому позицию заказа берём из payload Tilda
    (payment.products[0]). Фолбэк: 1 × payment_amount.
    """
    try:
        raw = order.raw_payload
        if not isinstance(raw, dict):
            return "1", _money(order.payment_amount)
        payment = raw.get("payment")
        if isinstance(payment, str):
            payment = json.loads(payment)
        products = payment.get("products") if isinstance(payment, dict) else None
        if isinstance(products, list) and products and isinstance(products[0], dict):
            item = products[0]
            qty = item.get("quantity")
            price = item.get("price") if item.get("price") is not None else item.get("amount")
            return str(qty) if qty is not None else "1", _money(price)
    except Exception:  # noqa: BLE001 — payload произвольный, не роняем отправку
        pass
    return "1", _money(order.payment_amount)


def build_data(order: OrderIn) -> dict:
    """Маппинг полей заказа -> переменные шаблона email.html."""
    day, month, year = _split_date(order.order_date)
    order_item_qty, order_item_price = _first_product(order)
    return {
        "name": order.customer_name or "",
        "email": order.customer_email or "",
        "day": day,
        "month": month,
        "year": year,
        "qty": order.qty or "1",
        "session": order.session_time or "",
        "format": EMAIL_FORMAT,
        "game": order.game or "",
        "tent": order.tent or "",
        "order_item_qty": order_item_qty,
        "order_item_price": order_item_price,
        "payment_amount": _money(order.payment_amount),
        "order_id": order.order_id,
        "payment_id": order.payment_transaction_id or "",
        "map_url": CLUB_MAP_URL,
        "club_phone": CLUB_PHONE,
        "club_messenger": CLUB_MESSENGER,
        "club_site": CLUB_SITE,
        "club_address": CLUB_ADDRESS,
    }


def render(template: str, data: dict) -> str:
    """Заменяет {{key}} значениями из data (как в примере пакета)."""
    for key, value in data.items():
        template = template.replace("{{" + key + "}}", str(value))
    return template


def smtp_enabled() -> bool:
    """True, если SMTP настроен (feature-флаг). Если False — отправка выключена."""
    return bool(os.getenv("SMTP_HOST"))


def _smtp_send(to_email: str, subject: str, html: str) -> None:
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER", "")
    smtp_password = os.environ.get("SMTP_PASSWORD", "")
    from_email = FROM_EMAIL or smtp_user
    from_name = FROM_NAME

    msg = MIMEMultipart("related")
    msg["Subject"] = str(Header(subject, "utf-8"))
    msg["From"] = f'{str(Header(from_name, "utf-8"))} <{from_email}>'
    msg["To"] = to_email

    alternative = MIMEMultipart("alternative")
    msg.attach(alternative)
    alternative.attach(
        MIMEText("Ваше бронирование подтверждено. Откройте письмо в HTML-режиме.", "plain", "utf-8")
    )
    alternative.attach(MIMEText(html, "html", "utf-8"))

    if HERO_PATH.exists():
        with open(HERO_PATH, "rb") as f:
            image = MIMEImage(f.read(), _subtype="png")
        image.add_header("Content-ID", "<zarnica-hero>")
        image.add_header("Content-Disposition", "inline", filename="zarnica-hero.png")
        msg.attach(image)

    context = ssl.create_default_context()
    if smtp_port == 465:
        server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30, context=context)
    else:
        server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
    with server:
        if smtp_port != 465:
            server.starttls(context=context)
        if smtp_user:
            server.login(smtp_user, smtp_password)
        server.send_message(msg)


def send_confirmation(order: OrderIn) -> str:
    """Отправляет письмо-подтверждение клиенту.

    Возвращает статус:
      'sent'     — письмо отправлено;
      'disabled' — SMTP не настроен (feature-флаг выключен);
      'no_email' — у заказа нет email.
    При ошибке SMTP бросает исключение (caller фиксирует её в логе статусов).
    """
    if not smtp_enabled():
        log.info("SMTP_HOST не задан — email-уведомления отключены")
        return "disabled"

    if not order.customer_email:
        log.info("заказ %s без email — письмо пропущено", order.order_id)
        return "no_email"

    subject = EMAIL_SUBJECT
    html = render(HTML_PATH.read_text(encoding="utf-8"), build_data(order))
    _smtp_send(order.customer_email, subject, html)
    log.info("confirmation email sent: order=%s to=%s", order.order_id, order.customer_email)
    return "sent"
