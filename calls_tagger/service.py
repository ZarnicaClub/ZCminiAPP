"""Цикл разметки: найти новые звонки без тегов, расшифровать, поставить теги.

Пишем всё в уже существующее поле `calls.metadata` (jsonb) — новых таблиц и миграций не нужно:

    metadata = {
      "tags": {"type": "корпоратив", "date": {...}, "players": {...}, "why": "корпоратив",
               "source": "rules-v1", "model": "whisper-small-int8", "tagged_at": "..."},
      "transcript": "текст разговора одной строкой",
      "transcript_model": "whisper-small-int8"
    }

Берём только **новые** звонки: окно по `call_datetime` (TAGGER_LOOKBACK_HOURS, по умолчанию 72).
Архивные записи сюда не попадают, старые теги не переписываются.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import time
import urllib.request
from datetime import datetime, timezone

from calls_tagger.tags import classify
from calls_tagger.transcribe import model_title, transcribe
from shared.db import pool

log = logging.getLogger("calls_tagger.service")

LOOKBACK_HOURS = int(os.getenv("TAGGER_LOOKBACK_HOURS") or "72")
BATCH = int(os.getenv("TAGGER_BATCH") or "20")

STATUS = {
    "service": "calls-tagger",
    "started_at": datetime.now(timezone.utc).isoformat(),
    "last_cycle_at": None,
    "selected": 0,
    "tagged": 0,
    "errors": 0,
    "last_error": None,
    "last": [],
}


def _audio_url(s3_key: str) -> str:
    """Публичная ссылка на файл в хранилище (бакет публичный, подпись не нужна)."""
    endpoint = (os.getenv("S3_ENDPOINT_URL") or "https://s3.twcstorage.ru").rstrip("/")
    bucket = os.getenv("S3_BUCKET_NAME") or ""
    return f"{endpoint}/{bucket}/{s3_key}"


def candidates(limit: int = BATCH):
    """Звонки без тегов за последние LOOKBACK_HOURS часов."""
    sql = """
        SELECT id, s3_key, call_datetime, duration_seconds
        FROM calls
        WHERE s3_key IS NOT NULL
          AND NOT (metadata ? 'tags')
          AND call_datetime >= now() - make_interval(hours => %s)
        ORDER BY call_datetime
        LIMIT %s
    """
    with pool().connection() as conn:
        return conn.execute(sql, (LOOKBACK_HOURS, limit)).fetchall()


def save_tags(call_id: int, tags: dict, transcript: str) -> None:
    sql = """
        UPDATE calls
        SET metadata = COALESCE(metadata, '{}'::jsonb) || jsonb_build_object(
                'tags', %s::jsonb,
                'transcript', %s::text,
                'transcript_model', %s::text,
                'tagged_at', %s::text
            )
        WHERE id = %s
    """
    payload = json.dumps(tags, ensure_ascii=False)
    with pool().connection() as conn:
        conn.execute(sql, (payload, transcript, model_title(),
                           datetime.now(timezone.utc).isoformat(), call_id))


def process_one(row, dry_run: bool = False) -> dict:
    """Один звонок: скачать -> расшифровать -> разметить -> сохранить."""
    call_id, s3_key, call_dt, dur = row[0], row[1], row[2], row[3]
    url = _audio_url(s3_key)
    tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tmp.close()
    try:
        with urllib.request.urlopen(url, timeout=180) as r, open(tmp.name, "wb") as f:
            f.write(r.read())
        started = time.time()
        text = transcribe(tmp.name)
        elapsed = time.time() - started
        tags = classify(text, call_dt.date())
        tags["model"] = model_title()
        tags["tagged_at"] = datetime.now(timezone.utc).isoformat()
        if not dry_run:
            save_tags(call_id, tags, text)
        log.info(
            "звонок #%s %s: тип=%s (по «%s»), дата=%s, игроков=%s, расшифровка %.0f с",
            call_id, call_dt.strftime("%d.%m %H:%M"), tags["type"], tags.get("why"),
            (tags.get("date") or {}).get("date") or "—",
            (tags.get("players") or {}).get("players") or "—", elapsed,
        )
        return {"id": call_id, "type": tags["type"], "date": (tags.get("date") or {}).get("date"),
                "players": (tags.get("players") or {}).get("players"), "seconds": round(elapsed)}
    finally:
        if os.path.exists(tmp.name):
            os.unlink(tmp.name)


def run_once(dry_run: bool = False) -> dict:
    """Один проход. Ошибка на одном звонке не срывает остальные."""
    STATUS["last_cycle_at"] = datetime.now(timezone.utc).isoformat()
    rows = candidates()
    STATUS["selected"] = len(rows)
    STATUS["tagged"] = 0
    STATUS["last"] = []
    for row in rows:
        try:
            res = process_one(row, dry_run=dry_run)
            STATUS["tagged"] += 1
            STATUS["last"].append(res)
        except Exception as e:  # noqa: BLE001
            STATUS["errors"] += 1
            STATUS["last_error"] = f"#{row[0]}: {type(e).__name__}: {e}"
            log.exception("звонок #%s не размечен: %s", row[0], e)
    log.info("цикл разметки: к обработке %s, размечено %s, ошибок %s",
             STATUS["selected"], STATUS["tagged"], STATUS["errors"])
    return STATUS
