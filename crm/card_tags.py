"""Согласованный тег карточки заказа: заказ — факт, звонки только уточняют.

Зачем: каждый звонок размечается отдельно, и в карточке рядом оказываются «просто игра, 12»,
«непонятно» и «корпоратив» из-за одной искажённой фразы. Артём (25.10.2026): «теги с каждым
новым звонком не менялись, а только уточнялись».

Правила:
- число игроков и дата игры — из оплаченного заказа (это факт, а не догадка модели);
- тип — большинство голосов среди звонков карточки; «непонятно» и «недозвон» не голосуют;
- при равенстве побеждает тип из более позднего звонка (порядок calls — от новых к старым);
- заказ от 30 человек делает карточку корпоративом (правило Артёма 11.10.2026);
- если данных нет вовсе — None, карточка показывает собственный тег звонка.
"""
from __future__ import annotations

from collections import Counter

# Типы, которые ничего не говорят о запросе и не должны влиять на карточку.
NEUTRAL_TYPES = {"непонятно", "недозвон"}
CORP_MIN_PLAYERS = 30


def _as_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_date(value):
    if not value:
        return None
    text = str(value)
    return text[:10]


def agreed_tags(calls, order=None):
    """Список звонков карточки (+ заказ) -> один согласованный тег или None."""
    calls = list(calls or [])
    order = order or {}

    players = _as_int(order.get("qty"))
    game_date = _as_date(order.get("order_date"))

    votes = Counter()
    first_seen = {}
    for index, call in enumerate(calls):          # 0 — самый свежий
        tags = call.get("tags") or {}
        kind = tags.get("type")
        if not kind or kind in NEUTRAL_TYPES:
            continue
        votes[kind] += 1
        first_seen.setdefault(kind, index)
        if players is None:
            players = _as_int((tags.get("players") or {}).get("players"))
        if game_date is None:
            game_date = _as_date((tags.get("date") or {}).get("date"))

    kind = None
    if votes:
        best = max(votes.values())
        tied = [k for k, v in votes.items() if v == best]
        kind = min(tied, key=lambda k: first_seen[k])   # равенство — более свежий звонок

    if kind in (None, "просто_игра") and players and players >= CORP_MIN_PLAYERS:
        kind = "корпоратив"

    if not kind and not players and not game_date:
        return None

    return {
        "type": kind,
        "date": ({"date": game_date, "kind": "order", "text": "дата игры из заказа"} if game_date else None),
        "players": ({"players": players, "text": f"{players} человек"} if players else None),
        "source": "card",
        "from_order": bool(order.get("order_id")),
    }
