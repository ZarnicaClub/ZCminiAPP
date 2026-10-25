# -*- coding: utf-8 -*-
"""Согласованный тег карточки: новый звонок уточняет, но не перебивает (13.18)."""
from crm.card_tags import agreed_tags


def call(kind=None, players=None, day=None):
    return {"tags": {"type": kind,
                     "players": {"players": players} if players else None,
                     "date": {"date": day} if day else None}}


ORDER_12 = {"order_id": "1554842592", "qty": "12", "order_date": "2026-10-25",
            "order_status": "paid"}


def test_заказ_даёт_число_и_дату_а_мусорный_звонок_не_понижает():
    """Карточка Матвея: три «просто игра, 12» и один «корпоратив» из искажённой фразы."""
    calls = [call("корпоратив"), call("непонятно"), call("просто_игра", 12, "2026-10-25"),
             call("просто_игра", 12, "2026-10-25")]
    result = agreed_tags(calls, ORDER_12)
    assert result["type"] == "просто_игра"
    assert result["players"]["players"] == 12
    assert result["date"]["date"] == "2026-10-25"
    assert result["from_order"] is True


def test_без_заказа_побеждает_большинство_а_непонятно_не_голосует():
    calls = [call("непонятно"), call("детский", 8, "2026-11-02"), call("детский", 8),
             call("просто_игра", 8)]
    result = agreed_tags(calls, None)
    assert result["type"] == "детский"
    assert result["players"]["players"] == 8
    assert result["date"]["date"] == "2026-11-02"
    assert result["from_order"] is False


def test_при_равенстве_побеждает_более_свежий_звонок():
    calls = [call("просто_игра", 10), call("корпоратив", 40)]   # первый — свежий
    assert agreed_tags(calls, None)["type"] == "просто_игра"


def test_большая_группа_из_заказа_делает_карточку_корпоративом():
    order = {"order_id": "1", "qty": 35, "order_date": "2026-11-01", "order_status": "paid"}
    result = agreed_tags([call("просто_игра", 35)], order)
    assert result["type"] == "корпоратив"


def test_совсем_пустая_карточка():
    assert agreed_tags([call()], None) is None
    assert agreed_tags([], None) is None
