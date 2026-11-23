"""crm: read-only запросы к PostgreSQL + presigned URL."""
import os
from datetime import date, datetime, timedelta, timezone

from psycopg.rows import dict_row

from shared.db import pool
from shared.s3 import presigned_url
from shared.serialize import json_safe, serialize_order, serialize_row
from crm.card_tags import agreed_tags


def _query(sql, params=None):
    with pool().connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params or ())
            return cur.fetchall()


def _tz_from_env():
    """Часовой пояс из CALL_TIMEZONE_OFFSET (по умолчанию +03:00)."""
    raw = (os.getenv("CALL_TIMEZONE_OFFSET") or "+03:00").strip()
    if not raw:
        raw = "+03:00"
    if raw[0] not in "+-":
        raw = "+" + raw
    sign = 1 if raw[0] == "+" else -1
    hh, mm = raw[1:].split(":")
    return timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))


def list_orders(status=None, event_date=None, limit=100):
    conditions, params = [], []
    if status:
        conditions.append("order_status = %s")
        params.append(status)
    if event_date:
        conditions.append("order_date = %s")
        params.append(event_date)
    where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
    params.append(limit)
    sql = f"""
        SELECT id, order_id, order_status, payment_amount, payment_currency,
               payment_system, payment_transaction_id, order_date,
               customer_name, customer_email, customer_phone, game, tent,
               session_time, qty, extra_fields, received_at, client_id
        FROM orders
        {where}
        ORDER BY received_at DESC NULLS LAST, id DESC
        LIMIT %s
    """
    return [serialize_order(r) for r in _query(sql, params)]


def get_order(order_id):
    rows = _query(
        """
        SELECT id, order_id, order_status, payment_amount, payment_currency,
               payment_system, payment_transaction_id, order_date,
               customer_name, customer_email, customer_phone, game, tent,
               session_time, qty, extra_fields, raw_payload, received_at, client_id
        FROM orders WHERE order_id = %s
        """,
        (order_id,),
    )
    return serialize_order(rows[0]) if rows else None


def _call_out(row):
    """Запись звонка для фронтенда: теги из metadata + временная ссылка на MP3.

    Расшифровку наружу не отдаём: на звонок это 1–3 КБ текста, а списку из 200 звонков
    она не нужна. Наружу идут только теги (`calls_tagger` их и кладёт в metadata.tags).
    """
    d = serialize_row(row)
    meta = d.pop("metadata", None) or {}
    d["tags"] = meta.get("tags")
    d["audio_url"] = presigned_url(d.get("s3_key"), expires=900)
    return d


def _orders_map(order_ids):
    """Заказы по их order_id: для согласованного тега нужны только qty и дата игры."""
    ids = [i for i in set(order_ids) if i]
    if not ids:
        return {}
    rows = _query(
        "SELECT order_id, qty, order_date, order_status FROM orders WHERE order_id = ANY(%s)",
        (ids,),
    )
    return {r["order_id"]: r for r in rows}


def _with_card_tags(calls, orders):
    """Проставить каждому звонку согласованный тег его карточки (tags_card)."""
    groups = {}
    for call in calls:
        order_id = call.get("order_id")
        if order_id:
            groups.setdefault(order_id, []).append(call)
    for order_id, group in groups.items():
        agreed = agreed_tags(group, orders.get(order_id))
        if agreed:
            for call in group:
                call["tags_card"] = agreed
    return calls


def order_calls(order_id):
    rows = _query(
        """
        SELECT id, email_id, order_id, phone, call_datetime, administrator,
               mp3_filename, s3_key, duration_seconds, status, created_at, metadata
        FROM calls WHERE order_id = %s
        ORDER BY call_datetime DESC, id DESC
        """,
        (order_id,),
    )
    calls = [_call_out(r) for r in rows]
    return _with_card_tags(calls, _orders_map([order_id]))


def get_order_bso(order_id):
    rows = _query(
        """
        SELECT id, order_id, game_date, order_amount, bso_number,
               players_fact, customer_name, rest_zone_amount,
               source, received_at, updated_at
        FROM orders_bso WHERE order_id = %s
        """,
        (order_id,),
    )
    return serialize_row(rows[0]) if rows else None


def client_bso(client_id):
    rows = _query(
        """
        SELECT b.id, b.order_id, b.game_date, b.order_amount, b.bso_number,
               b.players_fact, b.customer_name, b.rest_zone_amount,
               b.source, b.received_at, b.updated_at
        FROM orders_bso b
        JOIN orders o ON o.order_id = b.order_id
        WHERE o.client_id = %s
        ORDER BY b.game_date DESC NULLS LAST, b.id DESC
        """,
        (client_id,),
    )
    return [serialize_row(r) for r in rows]


def list_bso(limit=200):
    rows = _query(
        """
        SELECT b.id, b.order_id, b.game_date, b.order_amount, b.bso_number,
               b.players_fact, b.customer_name, b.rest_zone_amount,
               b.source, b.received_at, b.updated_at,
               o.customer_phone, o.client_id,
               o.payment_amount, o.order_status,
               o.customer_name AS order_customer_name
        FROM orders_bso b
        LEFT JOIN orders o ON o.order_id = b.order_id
        ORDER BY b.game_date DESC NULLS LAST, b.id DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [serialize_row(r) for r in rows]


def calendar():
    rows = _query(
        """
        SELECT order_date, COUNT(*) AS total,
               COUNT(*) FILTER (WHERE order_status = 'paid') AS paid
        FROM orders
        WHERE order_date IS NOT NULL AND order_date >= CURRENT_DATE
        GROUP BY order_date ORDER BY order_date LIMIT 60
        """
    )
    return [{"date": json_safe(r["order_date"]), "total": int(r["total"]), "paid": int(r["paid"])} for r in rows]


def list_clients(limit=200):
    rows = _query(
        """
        SELECT c.client_id, c.phone, c.name, c.email,
               COUNT(DISTINCT o.order_id) AS orders_count,
               COUNT(DISTINCT ca.id) AS calls_count,
               MAX(ca.call_datetime) AS last_call_at
        FROM clients c
        LEFT JOIN orders o ON o.client_id = c.client_id
        LEFT JOIN calls ca ON ca.client_id = c.client_id
        WHERE c.name IS NOT NULL
          AND c.name <> ''
          AND EXISTS (
              SELECT 1 FROM orders po
              WHERE po.client_id = c.client_id AND po.order_status = 'paid'
          )
        GROUP BY c.client_id
        ORDER BY last_call_at DESC NULLS LAST, COALESCE(c.name, c.phone)
        LIMIT %s
        """,
        (limit,),
    )
    return [serialize_row(r) for r in rows]


def client_calls(client_id):
    rows = _query(
        """
        SELECT id, email_id, order_id, phone, call_datetime, administrator,
               mp3_filename, s3_key, duration_seconds, status, created_at, metadata
        FROM calls WHERE client_id = %s
        ORDER BY call_datetime DESC, id DESC
        """,
        (client_id,),
    )
    calls = [_call_out(r) for r in rows]
    return _with_card_tags(calls, _orders_map([c.get("order_id") for c in calls]))


def unmatched_calls(limit=200):
    rows = _query(
        """
        SELECT id, email_id, order_id, phone, call_datetime, administrator,
               s3_key, duration_seconds, status, metadata
        FROM calls WHERE status = 'unmatched'
        ORDER BY call_datetime DESC, id DESC LIMIT %s
        """,
        (limit,),
    )
    return [_call_out(r) for r in rows]


def _day_bounds(date_str=None):
    """Границы суток (start, end) по часовому поясу CALL_TIMEZONE_OFFSET.

    date_str — ISO YYYY-MM-DD; если None или невалидна — «сегодня».
    """
    tz = _tz_from_env()
    day = None
    if date_str:
        try:
            day = date.fromisoformat(str(date_str))
        except ValueError:
            day = None
    if day:
        start = datetime(day.year, day.month, day.day, tzinfo=tz)
    else:
        now = datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=1)
    return start, end


def calls_today(limit=200, date_str=None):
    """Звонки за указанную дату (или за сегодня) по TZ CALL_TIMEZONE_OFFSET."""
    start, end = _day_bounds(date_str)
    rows = _query(
        """
        SELECT id, email_id, order_id, phone, call_datetime, administrator,
               mp3_filename, s3_key, duration_seconds, status, created_at, metadata
        FROM calls
        WHERE call_datetime >= %s AND call_datetime < %s
        ORDER BY call_datetime DESC, id DESC
        LIMIT %s
        """,
        (start.isoformat(), end.isoformat(), limit),
    )
    return [_call_out(r) for r in rows]


def weekend_headcount():
    """Сумма игроков (qty) оплаченных заказов с датой [сегодня .. ближайший понедельник]."""
    today = date.today()
    days_ahead = 7 - today.weekday()  # 1..7 -> ближайший будущий понедельник
    next_monday = today + timedelta(days=days_ahead)
    rows = _query(
        """
        SELECT qty
        FROM orders
        WHERE order_status = 'paid'
          AND order_date IS NOT NULL
          AND order_date >= %s
          AND order_date <= %s
        """,
        (today.isoformat(), next_monday.isoformat()),
    )
    total = 0
    for r in rows:
        raw = str(r.get("qty") or "").strip()
        try:
            total += int(raw)
        except ValueError:
            continue
    return total


def set_call_order(call_id, order_id):
    """Ручное связывание звонка с заказом (MANUAL_MATCH)."""
    with pool().connection() as conn:
        cur = conn.execute(
            "UPDATE calls SET order_id = %s, status = 'matched' WHERE id = %s",
            (order_id, call_id),
        )
        conn.commit()
        return cur.rowcount


# --- права на правки: белый список Telegram-ID (таблица crm_editors) ---

def get_editor(telegram_id):
    """Строка доступа для Telegram-ID или None (нет строки / отключён)."""
    rows = _query(
        """
        SELECT telegram_id, display_name, username, role, is_active, added_by, added_at
        FROM crm_editors
        WHERE telegram_id = %s AND is_active = true
        """,
        (telegram_id,),
    )
    return rows[0] if rows else None


def is_editor(telegram_id) -> bool:
    """Может ли этот Telegram-ID вносить правки. Закрыто по умолчанию."""
    if telegram_id is None:
        return False
    try:
        return get_editor(telegram_id) is not None
    except Exception:
        # Нет таблицы/базы — писать нельзя (fail-closed), чтение не страдает.
        return False


def list_editors():
    """Весь список доступов (включая отключённых) — для раздела «Доступы»."""
    return _query(
        """
        SELECT telegram_id, display_name, username, role, is_active, added_by, added_at
        FROM crm_editors
        ORDER BY added_at
        """
    )


# --- словари значений для выбора (из того, что уже есть в заказах) ---

def dictionaries():
    """Значения session_time / game / tent, которые уже встречались, по частоте."""
    rows = _query(
        """
        SELECT 'session_time' AS field, session_time AS value, count(*) AS n
          FROM orders WHERE coalesce(session_time, '') <> '' GROUP BY 1, 2
        UNION ALL
        SELECT 'game', game, count(*) FROM orders WHERE coalesce(game, '') <> '' GROUP BY 1, 2
        UNION ALL
        SELECT 'tent', tent, count(*) FROM orders WHERE coalesce(tent, '') <> '' GROUP BY 1, 2
        UNION ALL
        SELECT 'qty', qty, count(*) FROM orders WHERE coalesce(qty, '') <> '' GROUP BY 1, 2
        ORDER BY field, n DESC, value
        """
    )
    out = {"session_time": [], "game": [], "tent": [], "qty": []}
    for r in rows:
        out.setdefault(r["field"], []).append({"value": r["value"], "count": int(r["n"])})
    return out


# --- история правок заказа ---

EDIT_FIELDS = ("order_date", "session_time", "qty", "game", "tent")


def order_edits(order_id, limit=200):
    """История правок заказа (свежие сверху) с именем редактора."""
    rows = _query(
        """
        SELECT oe.id, oe.order_id, oe.field, oe.old_value, oe.new_value,
               oe.edited_by, oe.edited_at,
               coalesce(e.display_name, 'ID ' || oe.edited_by::text) AS editor_name
          FROM order_edits oe
          LEFT JOIN crm_editors e ON e.telegram_id = oe.edited_by
         WHERE oe.order_id = %s
         ORDER BY oe.edited_at DESC, oe.id DESC
         LIMIT %s
        """,
        (order_id, limit),
    )
    return [serialize_row(r) for r in rows]


def edit_order_fields(order_id, changes, edited_by):
    """Меняет сеанс/игроков/тариф/размещение и пишет по строке в журнал.

    changes — dict с любыми из EDIT_FIELDS (значения уже проверены вызывающим).
    Возвращает список фактических изменений [{field, old, new}] или None, если заказа нет.
    """
    with pool().connection() as conn:
        cur = conn.execute(
            "SELECT order_date, session_time, qty, game, tent FROM orders WHERE order_id = %s FOR UPDATE",
            (order_id,),
        )
        row = cur.fetchone()
        if row is None:
            return None
        old = dict(zip(EDIT_FIELDS, row))
        applied = []
        for field in EDIT_FIELDS:
            if field not in changes:
                continue
            new = changes[field]
            before = old.get(field)
            if (before if before is not None else "") == (new if new is not None else ""):
                continue
            if str(before if before is not None else "") == str(new):
                continue
            conn.execute(
                f"UPDATE orders SET {field} = %s WHERE order_id = %s",  # field из белого списка
                (new, order_id),
            )
            conn.execute(
                """
                INSERT INTO order_edits (order_id, field, old_value, new_value, edited_by)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    order_id,
                    field,
                    None if before is None else str(before),
                    None if new is None else str(new),
                    edited_by,
                ),
            )
            applied.append({"field": field, "old": before, "new": new})
        conn.commit()
        return applied


