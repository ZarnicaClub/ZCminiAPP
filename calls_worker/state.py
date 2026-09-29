"""Курсор воркера: до какого письма в ящике уже разобрано.

Зачем: без закладки воркер каждый цикл (раз в 5 минут) заново вычитывал всё
суточное окно и повторно скачивал тела писем вместе с MP3 — Яндекс на это
притормаживал соединение (`command: UID => problems with connection`).

Закладка — три числа: последний разобранный UID, отпечаток ящика (UIDVALIDITY)
и время записи. Лежит в файле рядом с кодом (`var/calls_worker_state.json`).

Потеря файла данные не теряет: следующий цикл отработает по суточному окну,
а уже разобранные письма отсеются по `email_id` (дубликаты в `calls` не попадут).
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("calls_worker.state")

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "var" / "calls_worker_state.json"


@dataclass
class Cursor:
    """Закладка: докуда дочитано и в каком «поколении» ящика."""

    last_uid: int
    uidvalidity: int | None = None
    updated_at: datetime | None = None


def state_path() -> Path:
    """Путь к файлу закладки (можно переопределить переменной WORKER_STATE_FILE)."""
    return Path(os.getenv("WORKER_STATE_FILE") or DEFAULT_PATH)


def load() -> Cursor | None:
    """Читает закладку. Нет файла или он битый → None (значит, работаем по окну)."""
    path = state_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        uid = int(data["last_uid"])
    except Exception as e:  # noqa: BLE001 — битый файл не должен ронять воркер
        log.warning("закладка не прочитана (%s): %s — цикл пойдёт по суточному окну", path, e)
        return None

    updated = None
    raw = data.get("updated_at")
    if raw:
        try:
            updated = datetime.fromisoformat(str(raw))
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
        except ValueError:
            updated = None

    uv = data.get("uidvalidity")
    try:
        uidvalidity = int(uv) if uv is not None else None
    except (TypeError, ValueError):
        uidvalidity = None
    return Cursor(last_uid=uid, uidvalidity=uidvalidity, updated_at=updated)


def save(last_uid, uidvalidity=None) -> Path:
    """Пишет закладку атомарно: сначала временный файл, потом подмена.

    Нужно, чтобы обрыв на середине записи не оставил половинчатый JSON.
    """
    path = state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "last_uid": int(last_uid),
        "uidvalidity": int(uidvalidity) if uidvalidity is not None else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".cursor-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path
