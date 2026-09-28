"""Тесты отправки писем через Yandex Cloud Postbox (без сети).

Проверяем то, что легко сломать: маппинг полей заказа в шаблон, структуру письма
(inline-картинка, тема, адреса), форму запроса к SESv2 и работу feature-флага.
Реальная отправка в тестах не выполняется — только подмена `_postbox_send`.
"""
from email.header import decode_header, make_header

import pytest

from shared import mailer
from shared.contracts import OrderIn


@pytest.fixture()
def order():
    return OrderIn(
        order_id="1241615321",
        order_status="paid",
        payment_amount=5000.0,
        payment_transaction_id="A-1234567890",
        order_date="2026-09-26",
        customer_name="Артём",
        customer_email="client@example.com",
        game="Пейнтбол 500 шаров",
        tent="Беседка №3",
        session_time="- Утренний с 9:00 до 14:45;",
        qty="5",
        raw_payload={"payment": {"products": [{"quantity": 5, "price": 1000}]}},
    )


def test_template_and_mapping(order):
    """Все плейсхолдеры подставлены, ключевые поля заказа в письме есть."""
    import re

    html = mailer.render(mailer.HTML_PATH.read_text(encoding="utf-8"), mailer.build_data(order))
    # служебный HTML-комментарий шаблона содержит пример {{...}} — сверяем тело без комментариев
    body = re.sub(r"<!--.*?-->", "", html, flags=re.S)

    assert "{{" not in body and "}}" not in body, "в письме остались незаполненные плейсхолдеры"
    assert "Артём" in html
    assert "26" in html and "СЕНТЯБРЯ" in html and "2026" in html
    assert "1241615321" in html          # номер заказа
    assert "5 000" in html               # сумма
    assert "Утренний с 9:00 до 14:45" in html, "сеанс должен выводиться без «- » и «;»"
    assert "- Утренний" not in html
    assert "Пейнтбол 500 шаров" in html  # тариф
    assert mailer.CLUB_PHONE in html
    assert mailer.CLUB_ADDRESS in html


def test_message_structure(order):
    """Письмо: тема, отправитель, ответ на рабочий ящик, картинка inline."""
    msg = mailer.build_message(order)

    # заголовки с русским текстом обязаны быть в RFC2047 (иначе Postbox отвергает письмо)
    assert str(make_header(decode_header(msg["From"]))) == "ЗарницаКлаб <noreply@send.zarnicaclub.ru>"
    assert str(make_header(decode_header(msg["Subject"]))) == mailer.EMAIL_SUBJECT
    assert msg["From"].startswith("=?utf-8?"), "имя отправителя должно быть закодировано"
    assert msg["To"] == "client@example.com"
    assert msg["Reply-To"] == "info@zarnicaclub.ru"

    types = [p.get_content_type() for p in msg.walk()]
    assert "multipart/alternative" in types
    assert "text/plain" in types and "text/html" in types
    assert "image/png" in types, "hero-картинка должна ехать внутри письма"

    image = [p for p in msg.walk() if p.get_content_type() == "image/png"][0]
    assert image["Content-ID"] == "<zarnica-hero>", "шаблон ссылается на cid:zarnica-hero"

    html_part = [p for p in msg.walk() if p.get_content_type() == "text/html"][0]
    html = html_part.get_payload(decode=True).decode("utf-8")
    assert "cid:zarnica-hero" in html
    assert "СЕНТЯБРЯ" in html


def test_send_request_is_raw_mime(order):
    """В Postbox уходит raw MIME (иначе теряется inline-картинка)."""
    msg = mailer.build_message(order)
    kwargs = mailer.send_request_kwargs(msg, order.customer_email)

    assert kwargs["FromEmailAddress"] == mailer.FROM_EMAIL
    assert kwargs["FromEmailAddress"].endswith("@send.zarnicaclub.ru")
    assert kwargs["Destination"]["ToAddresses"] == ["client@example.com"]
    assert kwargs["ReplyToAddresses"] == ["info@zarnicaclub.ru"]

    raw = kwargs["Content"]["Raw"]["Data"]
    assert isinstance(raw, bytes) and len(raw) > 0
    assert b"zarnica-hero" in raw


def test_disabled_without_keys(order, monkeypatch):
    """Без ключей письма не отправляются — и наружу это видно статусом 'disabled'."""
    monkeypatch.delenv("POSTBOX_KEY_ID", raising=False)
    monkeypatch.delenv("POSTBOX_SECRET", raising=False)
    assert mailer.email_enabled() is False
    assert mailer.send_confirmation(order) == "disabled"


def test_no_email(order, monkeypatch):
    monkeypatch.setenv("POSTBOX_KEY_ID", "YCAJE-test")
    monkeypatch.setenv("POSTBOX_SECRET", "secret")
    order.customer_email = None
    assert mailer.send_confirmation(order) == "no_email"


def test_send_confirmation_happy_path(order, monkeypatch):
    """При заданных ключах письмо уходит, статус 'sent' (сам вызов Postbox подменён)."""
    monkeypatch.setenv("POSTBOX_KEY_ID", "YCAJE-test")
    monkeypatch.setenv("POSTBOX_SECRET", "secret")

    calls = {}

    def fake_send(msg, to_email):
        calls["to"] = to_email
        calls["subject"] = msg["Subject"]
        calls["raw"] = msg.as_bytes()
        return "DLR05KED89K8.TEST@ingress1-vla"

    monkeypatch.setattr(mailer, "_postbox_send", fake_send)

    assert mailer.send_confirmation(order) == "sent"
    assert calls["to"] == "client@example.com"
    assert str(make_header(decode_header(calls["subject"]))) == mailer.EMAIL_SUBJECT
    # в raw MIME картинка едет вложением с этим Content-ID (в HTML она уже base64, поэтому ищем заголовок вложения)
    assert b"zarnica-hero" in calls["raw"]


def test_log_mail_config_says_disabled(monkeypatch, caplog):
    for var in ("POSTBOX_KEY_ID", "POSTBOX_SECRET"):
        monkeypatch.delenv(var, raising=False)
    with caplog.at_level("INFO", logger="shared.mailer"):
        mailer.log_mail_config()
    assert any("выключены" in r.message for r in caplog.records)
