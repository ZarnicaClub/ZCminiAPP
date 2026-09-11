"""crm: read-only запросы к PostgreSQL + presigned URL."""
import os
from datetime import date, datetime, timedelta, timezone

from psycopg.rows import dict_row

from shared.db import pool
from shared.s3 import presigned_url
from shared.serialize import json_safe, serialize_order, serialize_row


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
        ORDER BY order_date ASC NULLS LAST, session_time ASC NULLS LAST, id DESC
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


def order_calls(order_id):
    rows = _query(
        """
        SELECT id, email_id, order_id, phone, call_datetime, administrator,
               mp3_filename, s3_key, duration_seconds, status, created_at
        FROM calls WHERE order_id = %s
        ORDER BY call_datetime DESC, id DESC
        """,
        (order_id,),
    )
    out = []
    for r in rows:
        d = serialize_row(r)
        d["audio_url"] = presigned_url(d.get("s3_key"), expires=900)
        out.append(d)
    return out


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
               mp3_filename, s3_key, duration_seconds, status, created_at
        FROM calls WHERE client_id = %s
        ORDER BY call_datetime DESC, id DESC
        """,
        (client_id,),
    )
    out = []
    for r in rows:
        d = serialize_row(r)
        d["audio_url"] = presigned_url(d.get("s3_key"), expires=900)
        out.append(d)
    return out


def unmatched_calls(limit=200):
    rows = _query(
        """
        SELECT id, email_id, order_id, phone, call_datetime, administrator,
               s3_key, duration_seconds, status
        FROM calls WHERE status = 'unmatched'
        ORDER BY call_datetime DESC, id DESC LIMIT %s
        """,
        (limit,),
    )
    out = []
    for r in rows:
        d = serialize_row(r)
        d["audio_url"] = presigned_url(d.get("s3_key"), expires=900)
        out.append(d)
    return out


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
               mp3_filename, s3_key, duration_seconds, status, created_at
        FROM calls
        WHERE call_datetime >= %s AND call_datetime < %s
        ORDER BY call_datetime DESC, id DESC
        LIMIT %s
        """,
        (start.isoformat(), end.isoformat(), limit),
    )
    out = []
    for r in rows:
        d = serialize_row(r)
        d["audio_url"] = presigned_url(d.get("s3_key"), expires=900)
        out.append(d)
    return out


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
