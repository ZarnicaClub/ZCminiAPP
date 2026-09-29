"""IMAP-выборка писем: по закладке (UID), с суточным окном как страховкой.

Как работает:
  1. если есть закладка (и «поколение» ящика совпадает) — спрашиваем у ящика
     только то, что пришло ПОСЛЕ неё: `UID SEARCH UID <last+1>:*`;
  2. если закладки нет, она битая или сменился UIDVALIDITY — работаем как
     раньше, по дате (`SINCE`), с расширением окна до времени последнего разбора;
  3. перед скачиванием проверяем по таблице `calls`, каких UID там ещё нет
     (`email_id` = UID письма) — тела уже разобранных писем не качаем вообще;
  4. тела качаем только для новых UID.

Закладка двигается отдельно от разбора (см. `advance_cursor`): письма «не той
структуры» (без MP3 или с несколькими) закладку пропускают, иначе они качались
бы вечно; а вот сбой скачивания — нет, такое письмо повторим в следующем цикле.
"""
from __future__ import annotations

import email
import imaplib
import logging
import os
import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from calls_worker import state
from calls_worker.parser import parse_message, text_header
from shared.db import pool

log = logging.getLogger("calls_worker.imap")

# Насколько глубоко можно разматывать окно по дате, если закладка потерялась.
MAX_FALLBACK_HOURS = 24 * 30


class Selection:
    """Что выбрано в ящике за цикл и что из этого реально скачано."""

    def __init__(self):
        self.mode = "window"        # cursor — по закладке; window — по суточному окну
        self.uids: list[int] = []   # UID, попавшие в выборку
        self.to_download: list[int] = []  # из них те, которых нет в базе
        self.messages: list[dict] = []    # разобранные письма
        self.failed: list[int] = []       # UID со сбоем — повторим в следующем цикле
        self.skipped_known = 0      # уже есть в базе: тело не качали
        self.not_parsed = 0         # письма без нужного заголовка (в calls не пишутся)
        self.uidvalidity: int | None = None
        self.uidvalidity_before: int | None = None
        self.total_in_folder: int | None = None
        self.max_uid: int | None = None
        self.cursor_before: int | None = None


def known_email_ids(uids) -> set[str]:
    """Какие из UID уже разобраны (есть строка в calls)."""
    ids = [str(u) for u in uids]
    if not ids:
        return set()
    with pool().connection() as conn:
        rows = conn.execute(
            "SELECT email_id FROM calls WHERE email_id = ANY(%s)", (ids,)
        ).fetchall()
    return {r[0] for r in rows}


def _uidvalidity(imap) -> int | None:
    """UIDVALIDITY ящика: берём из ответа на выбор папки, без лишних запросов."""
    for raw in imap.untagged_responses.get("UIDVALIDITY", []) or []:
        text = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
        m = re.search(r"(\d+)", text)
        if m:
            return int(m.group(1))
    return None


def _folder_total(imap) -> int | None:
    for raw in imap.untagged_responses.get("EXISTS", []) or []:
        text = raw.decode(errors="replace") if isinstance(raw, bytes) else str(raw)
        m = re.search(r"(\d+)", text)
        if m:
            return int(m.group(1))
    return None


def _search(imap, key: str, value: str) -> list[int]:
    status, data = imap.uid("search", None, key, value)
    if status != "OK":
        raise RuntimeError(f"IMAP UID search failed ({key} {value})")
    if not data or not data[0]:
        return []
    return sorted(int(x) for x in data[0].split())


def _msg_datetime(msg):
    try:
        dt = parsedate_to_datetime(text_header(msg.get("Date")))
    except Exception:  # noqa: BLE001 — кривую дату просто игнорируем
        return None
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _fallback_since(cursor, hours: int) -> datetime:
    """Начало окна при разборе по дате.

    Обычно это «сейчас минус N часов». Но если закладка есть, а работать по ней
    нельзя (сменился UIDVALIDITY или она старше окна), окно расширяем до времени
    последнего разбора с запасом в сутки — так простой не съедает письма.
    Глубже 30 суток не лезем, чтобы не вычитывать ящик целиком.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)
    if cursor is not None and cursor.updated_at is not None:
        since = min(since, cursor.updated_at - timedelta(hours=24))
    return max(since, now - timedelta(hours=MAX_FALLBACK_HOURS))


def fetch_new_messages(lookback_hours=None) -> Selection:
    """Один проход по ящику: что нового и какие письма разобрать."""
    hours = int(lookback_hours or os.getenv("PARSER_LOOKBACK_HOURS") or "24")
    cursor = state.load()

    host = os.getenv("MAIL_IMAP_HOST", "imap.yandex.ru")
    port = int(os.getenv("MAIL_IMAP_PORT") or "993")
    user = os.environ["MAIL_USERNAME"]
    password = os.environ["MAIL_PASSWORD"]
    folder = os.getenv("MAIL_FOLDER", "INBOX")

    sel = Selection()
    sel.cursor_before = cursor.last_uid if cursor else None
    sel.uidvalidity_before = cursor.uidvalidity if cursor else None

    imap = imaplib.IMAP4_SSL(host, port)
    try:
        imap.login(user, password)
        status, _ = imap.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError("cannot select mailbox readonly")
        sel.uidvalidity = _uidvalidity(imap)
        sel.total_in_folder = _folder_total(imap)

        same_epoch = (
            sel.uidvalidity is None
            or cursor is None
            or cursor.uidvalidity is None
            or cursor.uidvalidity == sel.uidvalidity
        )
        since_dt = None
        if cursor is not None and cursor.last_uid > 0 and same_epoch:
            sel.mode = "cursor"
            # `n:*` по стандарту отдаёт как минимум последнее письмо ящика,
            # поэтому всё, что не больше закладки, отсекаем сами.
            sel.uids = [u for u in _search(imap, "UID", f"{cursor.last_uid + 1}:*")
                        if u > cursor.last_uid]
        else:
            sel.mode = "window"
            if cursor is not None and not same_epoch:
                log.warning("поколение ящика сменилось (UIDVALIDITY %s → %s) — закладку сбрасываю",
                            cursor.uidvalidity, sel.uidvalidity)
            since_dt = _fallback_since(cursor, hours)
            sel.uids = _search(imap, "SINCE", since_dt.strftime("%d-%b-%Y"))

        sel.max_uid = sel.uids[-1] if sel.uids else None

        known = known_email_ids(sel.uids)
        sel.skipped_known = sum(1 for u in sel.uids if str(u) in known)
        sel.to_download = [u for u in sel.uids if str(u) not in known]

        for uid in sel.to_download:
            try:
                status, raw = imap.uid("fetch", str(uid), "(RFC822)")
                if status != "OK" or not raw or not raw[0]:
                    raise RuntimeError(f"fetch вернул {status}")
                raw_bytes = raw[0][1]
                msg = email.message_from_bytes(raw_bytes)
                if since_dt is not None:
                    # SINCE имеет дневную гранулярность — уточняем по дате письма
                    dt = _msg_datetime(msg)
                    if dt is not None and dt < since_dt:
                        continue
                parsed = parse_message(raw_bytes, str(uid))
                if not parsed:
                    sel.not_parsed += 1
                    continue
                sel.messages.append(parsed)
            except Exception as e:  # noqa: BLE001 — сбой письма не должен ронять цикл
                log.warning("письмо UID %s не скачано: %s — повторю в следующем цикле", uid, e)
                sel.failed.append(uid)

        return sel
    finally:
        try:
            imap.logout()
        except Exception:  # noqa: BLE001
            pass


def advance_cursor(sel: Selection) -> int | None:
    """Двигает закладку по итогам цикла; возвращает новое значение (или None).

    Правила:
      * сбой на письме — закладку за него не пускаем (это письмо повторим);
      * письма «не той структуры» сбой не считаются: закладка их пропускает,
        иначе они качались бы каждый цикл вечно;
      * назад закладка не едет.
    """
    limit = None
    if sel.failed:
        limit = min(sel.failed) - 1
    elif sel.max_uid is not None:
        limit = sel.max_uid
    if limit is None:
        return None                     # новых писем не было — файл не трогаем

    epoch_changed = (
        sel.uidvalidity is not None
        and sel.uidvalidity_before is not None
        and sel.uidvalidity != sel.uidvalidity_before
    )
    # назад закладка не едет — кроме случая, когда сменилось поколение ящика:
    # там старый номер к новому ящику отношения не имеет.
    if not epoch_changed and sel.cursor_before is not None and limit <= sel.cursor_before:
        return None

    state.save(limit, sel.uidvalidity)
    return limit
