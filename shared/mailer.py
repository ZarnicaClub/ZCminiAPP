"""Отправка email-уведомлений (подтверждение брони) через Yandex Cloud Postbox.

Транспорт — HTTP API Postbox (совместим с Amazon SESv2), порт 443: исходящие
почтовые порты на Timeweb App Platform закрыты (blocked_ports: 25/465/587/2525),
поэтому SMTP с платформы физически не работает (проверено 25.09.2026: из 64
оплаченных заказов не ушло ни одного письма).

Письмо собирается как raw MIME (MIMEMultipart('related')) — это нужно, чтобы
hero-картинка уходила inline с Content-ID: <zarnica-hero>, а не ссылкой на сайт.
Новых зависимостей нет: boto3 уже используется для S3 (shared/s3.py).

Правила безопасности:
- feature-флаг: нет POSTBOX_KEY_ID/POSTBOX_SECRET — ничего не отправляем (только лог);
- рендер и отправка вынесены сюда, БД здесь не трогаем (идемпотентность — в caller);
- ошибка отправки бросается наружу, чтобы caller снял флаг confirmation_sent_at;
- короткие таймауты: письмо — best-effort побочный эффект и не должно держать
  фоновую задачу (а через неё — ответ вебхука Tilda).
"""
import json
import logging
import os
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
# В окружении остаются только ключи Postbox: POSTBOX_KEY_ID/POSTBOX_SECRET.
# ---------------------------------------------------------------------
FROM_NAME = "ЗарницаКлаб"
FROM_EMAIL = "noreply@send.zarnicaclub.ru"  # подтверждённый домен Postbox (Easy DKIM)
REPLY_TO = "info@zarnicaclub.ru"            # ответы клиентов идут на рабочий ящик клуба
# Тема без повтора названия клуба: в списке писем под отправителем «ЗарницаКлаб» сразу видно
# «Ваше бронирование подтверждено» (Артём, 28.09.2026).
EMAIL_SUBJECT = "Ваше бронирование подтверждено"
EMAIL_FORMAT = "Пейнтбол"
CLUB_MAP_URL = "https://yandex.ru/maps/-/CTXRbV3W"
CLUB_PHONE = "+7 (495) 212-12-23"                      # подтверждён Артёмом 28.09.2026
CLUB_MESSENGER = "Telegram / WhatsApp"  # заглушка: Артём решит позже (28.09.2026).
# В шаблоне строка выводится как есть ({{club_messenger}}), без подписи-дубля: когда появится
# реальный контакт, значение станет, например, «Telegram: @zarnicaclub».
CLUB_SITE = "ЗарницаКлаб.рф"                # сайт с онлайн-кассой Т-Банк; в зоне .рф
CLUB_ADDRESS = "МО, Новая Рига 30км, ЦКАД"                   # подтверждён 28.09.2026

# Postbox (SESv2-совместимый эндпоинт). Регион обязателен для подписи запроса.
POSTBOX_ENDPOINT = os.getenv("POSTBOX_ENDPOINT", "https://postbox.cloud.yandex.net")
POSTBOX_REGION = os.getenv("POSTBOX_REGION", "ru-central1")


def _env_timeout() -> float:
    """POSTBOX_TIMEOUT из окружения (сек)."""
    try:
        value = float(os.getenv("POSTBOX_TIMEOUT", "10"))
    except (TypeError, ValueError):
        log.warning("POSTBOX_TIMEOUT задан неверно — использую 10 с")
        return 10.0
    return value if value > 0 else 10.0


# Таймаут ожидания ответа Postbox (сек). Подключение — 5 с.
POSTBOX_TIMEOUT = _env_timeout()


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
        "session": (order.session_time or "").strip().rstrip(";").strip(),
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


def email_enabled() -> bool:
    """True, если Postbox настроен (feature-флаг). Если False — отправка выключена."""
    return bool(os.getenv("POSTBOX_KEY_ID")) and bool(os.getenv("POSTBOX_SECRET"))


def log_mail_config() -> None:
    """Разовая диагностика отправки писем в логе старта сервиса.

    Показывает, включена ли отправка, с какого адреса и куда шлём, какие адреса
    отдаёт DNS, и на месте ли шаблон с картинкой. Этого достаточно, чтобы отличить
    «ключи не заданы» / «нет шаблона» / «эндпоинт недоступен» без доступа в контейнер.
    """
    if not email_enabled():
        log.info("письма: выключены (POSTBOX_KEY_ID/POSTBOX_SECRET не заданы)")
        return
    key_id = os.getenv("POSTBOX_KEY_ID", "")
    try:
        import socket

        endpoint_host = POSTBOX_ENDPOINT.replace("https://", "").split("/")[0]
        ipv4 = sorted({i[4][0] for i in socket.getaddrinfo(endpoint_host, 443, socket.AF_INET, socket.SOCK_STREAM)})
    except Exception as exc:  # noqa: BLE001 — диагностика не должна мешать старту
        ipv4 = ["ошибка: %s" % exc]
    log.info(
        "письма: вкл | отправитель=%s reply-to=%s | postbox=%s (%s, ipv4=%s) timeout=%ss | ключ …%s | "
        "шаблон=%s картинка=%s",
        FROM_EMAIL, REPLY_TO, POSTBOX_ENDPOINT, POSTBOX_REGION, ipv4, POSTBOX_TIMEOUT,
        key_id[-4:], HTML_PATH.exists(), HERO_PATH.exists(),
    )


# ---------------------------------------------------------------------
# Почтовая часть
# ---------------------------------------------------------------------
def build_message(order: OrderIn) -> MIMEMultipart:
    """Собирает письмо: тема, адреса, HTML-версия, текстовая версия, inline-hero."""
    html = render(HTML_PATH.read_text(encoding="utf-8"), build_data(order))

    msg = MIMEMultipart("related")
    # ВАЖНО: именно .encode(), а не str(Header(...)) — str() возвращает некодированную
    # строку, и в заголовке уезжает сырой UTF-8, который Postbox отвергает
    # («email address parse failed (From)», проверено 28.09.2026).
    msg["Subject"] = Header(EMAIL_SUBJECT, "utf-8").encode()
    msg["From"] = f'{Header(FROM_NAME, "utf-8").encode()} <{FROM_EMAIL}>'
    msg["To"] = order.customer_email or ""
    if REPLY_TO:
        msg["Reply-To"] = REPLY_TO

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
    return msg


def send_request_kwargs(msg: MIMEMultipart, to_email: str) -> dict:
    """Аргументы вызова SESv2 SendEmail (чистая функция — удобно тестировать).

    Raw-письмо, а не Simple: только так остаётся inline-картинка с cid:zarnica-hero.
    """
    return {
        "FromEmailAddress": FROM_EMAIL,
        "Destination": {"ToAddresses": [to_email]},
        "ReplyToAddresses": [REPLY_TO] if REPLY_TO else [],
        "Content": {"Raw": {"Data": msg.as_bytes()}},
    }


def _client():
    """Клиент Postbox (boto3 sesv2). Импорт boto3 — ленивый, чтобы не тормозить старт."""
    import boto3
    from botocore.config import Config

    return boto3.client(
        "sesv2",
        region_name=POSTBOX_REGION,
        endpoint_url=POSTBOX_ENDPOINT,
        aws_access_key_id=os.getenv("POSTBOX_KEY_ID"),
        aws_secret_access_key=os.getenv("POSTBOX_SECRET"),
        config=Config(connect_timeout=5, read_timeout=POSTBOX_TIMEOUT,
                      retries={"max_attempts": 2, "mode": "standard"}),
    )


def _postbox_send(msg: MIMEMultipart, to_email: str) -> str:
    """Отправляет готовое письмо через Postbox, возвращает MessageId."""
    response = _client().send_email(**send_request_kwargs(msg, to_email))
    return str(response.get("MessageId", ""))


def send_confirmation(order: OrderIn) -> str:
    """Отправляет письмо-подтверждение клиенту.

    Возвращает статус:
      'sent'     — письмо отправлено;
      'disabled' — Postbox не настроен (feature-флаг выключен);
      'no_email' — у заказа нет email.
    При ошибке отправки бросает исключение (caller снимает флаг и пишет в лог).
    """
    if not email_enabled():
        log.info("POSTBOX_KEY_ID/POSTBOX_SECRET не заданы — email-уведомления отключены")
        return "disabled"

    if not order.customer_email:
        log.info("заказ %s без email — письмо пропущено", order.order_id)
        return "no_email"

    message = build_message(order)
    message_id = _postbox_send(message, order.customer_email)
    log.info("confirmation email sent: order=%s to=%s message_id=%s",
             order.order_id, order.customer_email, message_id)
    return "sent"
