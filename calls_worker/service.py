"""calls-worker: цикл обработки (advisory lock, матчинг, S3, Calls).

Цикл больше не перечитывает всё окно: `fetch_new_messages` отдаёт только новое
(по закладке — см. `calls_worker/state.py`), а тела писем качаются лишь для тех
UID, которых нет в таблице `calls`.
"""
import io
import json
import logging
import time
from datetime import datetime, timezone

from calls_worker.imap import advance_cursor, fetch_new_messages
from calls_worker.parser import match_status, mp3_duration
from shared.db import pool
from shared.s3 import build_s3_key, s3_client

log = logging.getLogger("calls_worker.service")
LOCK_ID = 783011

# Счётчики накопительные с момента запуска процесса (приросты за цикл — в last_cycle).
STATUS = {
    "service": "calls-worker",
    "last_cycle_at": None,
    "mode": None,          # cursor — по закладке; window — по суточному окну
    "last_uid": None,      # докуда разобрано (закладка)
    "selected": 0,         # UID в выборке
    "downloaded": 0,       # тел писем скачано
    "skipped": 0,          # уже было в базе — тело не качали
    "processed": 0,        # письма, взятые в разбор
    "inserted": 0,         # записано в таблицу calls
    "matched": 0,          # привязано к заказу
    "unmatched": 0,        # заказ по телефону не найден
    "ambiguous": 0,        # телефон найден у нескольких заказов
    "duplicates": 0,       # такой MP3/письмо уже в базе
    "malformed": 0,        # письмо не той структуры (нет MP3 или их несколько)
    "errors": 0,
    "last_error": None,
    "last_cycle": {},
}


def _existing(email_ids, hashes):
    """Возвращает (set email_id, set mp3_hash) уже присутствующих в БД."""
    with pool().connection() as conn:
        eids = set()
        if email_ids:
            eids = {r[0] for r in conn.execute(
                "SELECT email_id FROM calls WHERE email_id = ANY(%s)",
                (list(email_ids),),
            ).fetchall()}
        hs = set()
        if hashes:
            hs = {r[0] for r in conn.execute(
                "SELECT mp3_hash FROM calls WHERE mp3_hash = ANY(%s)",
                (list(hashes),),
            ).fetchall()}
    return eids, hs


def _order_ids_for_phone(phone):
    with pool().connection() as conn:
        rows = conn.execute(
            "SELECT order_id FROM orders WHERE customer_phone = %s ORDER BY order_id",
            (phone,),
        ).fetchall()
    return [r[0] for r in rows]


def process_one(msg, s3, bucket, existing_eids, existing_hashes):
    """Обрабатывает одно письмо.

    action: inserted — записали в базу; skipped_duplicate — такое уже есть;
    malformed — структура письма не та (в базу не пишется, закладка пройдёт мимо);
    error — файл не разобрался (тоже постоянное, повторов не требуем).
    """
    parsed = msg["parsed"]
    atts = msg["attachments"]
    rec = {"email_id": msg["email_id"], "status": None, "action": None, "error": None}

    if len(atts) != 1:
        rec["action"] = "malformed"
        rec["error"] = ("вложений больше одного" if len(atts) > 1
                        else "в письме нет MP3")
        return rec

    att = atts[0]
    if msg["email_id"] in existing_eids or att["sha256"] in existing_hashes:
        rec["action"] = "skipped_duplicate"
        return rec

    try:
        dur = mp3_duration(att["payload"])
    except Exception as e:  # noqa: BLE001
        rec["action"] = "error"
        rec["error"] = f"mp3 duration: {e}"
        return rec

    order_ids = _order_ids_for_phone(parsed["phone"])
    status = match_status(order_ids)
    order_id = order_ids[0] if len(order_ids) == 1 else None

    key = build_s3_key(att["sha256"])
    s3.upload_fileobj(
        io.BytesIO(att["payload"]), bucket, key,
        ExtraArgs={"ContentType": "audio/mpeg"},
    )

    with pool().connection() as conn:
        conn.execute(
            """
            INSERT INTO calls (
                email_id, order_id, phone, call_datetime, administrator,
                mp3_filename, s3_key, duration_seconds, status, metadata,
                client_id, mp3_hash
            ) VALUES (
                %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,
                (SELECT client_id FROM clients WHERE phone=%s), %s
            )
            ON CONFLICT DO NOTHING
            """,
            (
                msg["email_id"], order_id, parsed["phone"], parsed["call_datetime"],
                parsed["administrator"], att["filename"], key, dur, status,
                json.dumps(
                    {"sha256": att["sha256"], "subject": msg["subject"]},
                    ensure_ascii=False,
                ),
                parsed["phone"], att["sha256"],
            ),
        )
        conn.commit()

    rec["status"] = status
    rec["action"] = "inserted"
    return rec


def run_once():
    """Один цикл; обновляет STATUS."""
    with pool().connection() as lock_conn:
        got = lock_conn.execute("SELECT pg_try_advisory_lock(%s)", (LOCK_ID,)).fetchone()[0]
        if not got:
            log.info("cycle skipped: another run holds the lock")
            return
        try:
            _run_cycle()
        finally:
            lock_conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


def _count(cycle, key, n=1):
    cycle[key] = cycle.get(key, 0) + n


def _run_cycle():
    started = time.time()
    STATUS["last_cycle_at"] = datetime.now(timezone.utc).isoformat()

    sel = fetch_new_messages()
    STATUS["mode"] = sel.mode
    STATUS["selected"] += len(sel.uids)
    STATUS["downloaded"] += len(sel.to_download)
    STATUS["skipped"] += sel.skipped_known

    cycle = {
        "mode": sel.mode,
        "selected": len(sel.uids),
        "downloaded": len(sel.to_download),
        "skipped": sel.skipped_known,
        "in_folder": sel.total_in_folder,
        "processed": 0, "inserted": 0, "matched": 0, "unmatched": 0,
        "ambiguous": 0, "duplicates": 0, "malformed": 0, "errors": 0,
    }

    email_ids = {m["email_id"] for m in sel.messages}
    hashes = {a["sha256"] for m in sel.messages for a in m["attachments"]}
    eids, hs = _existing(email_ids, hashes)

    s3, bucket = s3_client()
    for m in sel.messages:
        try:
            rec = process_one(m, s3, bucket, eids, hs)
        except Exception as e:  # noqa: BLE001 — сбой (БД/S3) не должен терять письмо
            err = f"{type(e).__name__}: {e}"
            STATUS["errors"] += 1
            STATUS["last_error"] = err
            _count(cycle, "errors")
            if sel.mode == "cursor":
                sel.failed.append(int(m["email_id"]))
            log.exception("письмо %s не обработано — повторю в следующем цикле: %s",
                          m["email_id"], e)
            continue

        STATUS["processed"] += 1
        _count(cycle, "processed")
        action = rec["action"]
        if action == "inserted":
            STATUS["inserted"] += 1
            _count(cycle, "inserted")
            if rec["status"] in ("matched", "unmatched", "ambiguous"):
                STATUS[rec["status"]] += 1
                _count(cycle, rec["status"])
        elif action == "skipped_duplicate":
            STATUS["duplicates"] += 1
            _count(cycle, "duplicates")
        elif action == "malformed":
            STATUS["malformed"] += 1
            _count(cycle, "malformed")
        if rec.get("error"):
            STATUS["errors"] += 1
            STATUS["last_error"] = rec["error"]
            _count(cycle, "errors")

    new_cursor = advance_cursor(sel)
    STATUS["last_uid"] = new_cursor if new_cursor is not None else sel.cursor_before

    cycle["seconds"] = round(time.time() - started, 1)
    STATUS["last_cycle"] = cycle

    log.info(
        "цикл за %.1f с (%s): в выборке %s, к скачиванию %s, скачано %s, уже было %s, "
        "сохранено %s, привязано %s, без пары %s, брак %s, ошибок %s, закладка %s",
        cycle["seconds"], cycle["mode"], cycle["selected"], cycle["downloaded"],
        cycle["processed"], cycle["skipped"], cycle["inserted"], cycle["matched"],
        cycle["unmatched"], cycle["malformed"], cycle["errors"], STATUS["last_uid"],
    )
