"""Тесты забора БСО из Google Sheets (без сети).

Проверяем чистые функции: разбор даты, поиск колонок по заголовкам и отбор строк —
правила повторяют старый Apps Script (`gsheets_webhook/apps_script.gs`).
"""
import pytest

from orders_webhook import gsheets_pull as gp


@pytest.mark.parametrize("raw,expected", [
    ("13.08.2026", "2026-08-13"),
    ("03.10.2026", "2026-10-03"),
    ("13.08.26", "2026-08-13"),      # короткий год из таблицы
    ("2026-08-13", "2026-08-13"),    # если кто-то вписал ISO
    ("1.9.2026", "2026-09-01"),      # без ведущих нулей
    ("", None),
    ("не дата", None),
    ("32.13.2026", None),
])
def test_iso_date(raw, expected):
    assert gp.iso_date(raw) == expected


HEADERS = ["год", "Месяц", "Дата", "Статья", "Приход", "order_id", "Расход",
           "№\nдокумента", "игроков (факт)", "Заказчик", "Зона отдыха"]


def test_header_index_tolerates_newlines():
    idx = gp.header_index(HEADERS)
    assert idx["date"] == 2 and idx["article"] == 3 and idx["income"] == 4
    assert idx["docNumber"] == 7      # «№\nдокумента» находится
    assert idx["playersFact"] == 8
    assert idx["orderId"] == 5


def test_header_index_reports_missing():
    with pytest.raises(RuntimeError) as e:
        gp.header_index(["Дата", "Приход"])
    assert "Статья" in str(e.value)


def _row(date="13.08.2026", article="Касса", income="19 000 ₽", doc="1449",
         players="8", customer="Юля", restzone="", order_id="1624763921"):
    row = [""] * len(HEADERS)
    row[2] = date
    row[3] = article
    row[4] = income
    row[5] = order_id
    row[7] = doc
    row[8] = players
    row[9] = customer
    row[10] = restzone
    return row


def test_iter_payloads_filters_like_apps_script():
    values = [
        HEADERS,
        _row(),                                     # подходит
        _row(article="Сбер"),                       # не Касса
        _row(date="01.08.2026"),                    # раньше 13.08.2026
        _row(order_id=""),                          # без order_id
        _row(date="10.10.2026", article="Касса", income="5 000,50 ₽", doc="1500",
             players="15", customer="Фёдор", restzone="3 000", order_id="1241615321 "),
    ]
    rows = list(gp.iter_payloads(values, date_from="2026-08-13"))
    assert [r["order_id"] for r in rows] == ["1624763921", "1241615321"]
    assert rows[0]["game_date"] == "2026-08-13"
    assert rows[0]["_row"] == 2
    assert rows[1]["_row"] == 6 and rows[1]["order_amount"] == "5 000,50"


def test_payload_parses_into_bso_contract():
    """То, что отдаёт забор, должно разбираться тем же парсером, что и payload скрипта."""
    from shared.gsheets import parse_gsheets_bso

    values = [HEADERS, _row(income="19 000 ₽", restzone="2 500 ₽")]
    payload = next(iter(gp.iter_payloads(values)))
    payload.pop("_row")
    bso = parse_gsheets_bso(payload)
    assert bso is not None
    assert bso.order_id == "1624763921"
    assert bso.order_amount == 19000.0
    assert bso.rest_zone_amount == 2500.0
    assert bso.players_fact == 8
    assert bso.bso_number == "1449"
    assert bso.customer_name == "Юля"


def test_enabled_requires_flag_and_key(monkeypatch):
    monkeypatch.delenv("GSHEETS_PULL_ENABLED", raising=False)
    monkeypatch.delenv("GSHEETS_SA_B64", raising=False)
    assert gp.enabled() is False
    monkeypatch.setenv("GSHEETS_PULL_ENABLED", "1")
    assert gp.enabled() is False, "без ключа робота забор не включаем"
