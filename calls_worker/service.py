"""calls-worker: цикл обработки (advisory lock, матчинг, S3, Calls)."""
import io
import json
import logging
from datetime import datetime, timezone

from calls_worker.imap import fetch_new_messages
from calls_worker.parser import match_status, mp3_duration
from shared.db import pool
from shared.s3 import build_s3_key, s3_client

log = logging.getLogger("calls_worker.service")
LOCK_ID = 783011

STATUS = {
    "service": "calls-worker",
    "last_cycle_at": None,
    "processed": 0,
    "inserted": 0,
    "matched": 0,
    "unmatched": 0,
    "ambiguous": 0,
    "errors": 0,
    "last_error": None,
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
    """Обрабатывает одно письмо; возвращает dict с результатом."""
    parsed = msg["parsed"]
    atts = msg["attachments"]
    rec = {
        "email_id": msg["email_id"], "status": "unmatched",
        "action": None, "error": None,
    }

    if len(atts) != 1:
        rec["status"] = "ambiguous" if len(atts) > 1 else "unmatched"
        rec["error"] = "expected exactly one MP3"
        return rec

    att = atts[0]
    if msg["email_id"] in existing_eids or att["sha256"] in existing_hashes:
        rec["action"] = "skipped_duplicate"
        return rec

    try:
        dur = mp3_duration(att["payload"])
    except Exception as e:  # noqa: BLE001
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


def _run_cycle():
    STATUS["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
    messages = fetch_new_messages()

    email_ids = {m["email_id"] for m in messages}
    hashes = {a["sha256"] for m in messages for a in m["attachments"]}
    eids, hs = _existing(email_ids, hashes)

    s3, bucket = s3_client()
    for m in messages:
        rec = process_one(m, s3, bucket, eids, hs)
        STATUS["processed"] += 1
        if rec["action"] == "inserted":
            STATUS["inserted"] += 1
        if rec.get("error"):
            STATUS["errors"] += 1
            STATUS["last_error"] = rec["error"]
        if rec["status"] in STATUS:
            STATUS[rec["status"]] += 1
    log.info("cycle done: %s messages", len(messages))
