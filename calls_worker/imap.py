"""IMAP-выборка писем по UID (НЕ по sequence number)."""
import email
import imaplib
import os
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from calls_worker.parser import parse_message, text_header


def fetch_new_messages(lookback_hours=None):
    """Возвращает список распарсенных сообщений (email_id = IMAP UID) за окно."""
    hours = int(lookback_hours or os.getenv("PARSER_LOOKBACK_HOURS", "24"))
    since_dt = datetime.now(timezone.utc) - timedelta(hours=hours)
    since_date = since_dt.strftime("%d-%b-%Y")

    host = os.getenv("MAIL_IMAP_HOST", "imap.yandex.ru")
    port = int(os.getenv("MAIL_IMAP_PORT", "993"))
    user = os.environ["MAIL_USERNAME"]
    password = os.environ["MAIL_PASSWORD"]
    folder = os.getenv("MAIL_FOLDER", "INBOX")

    imap = imaplib.IMAP4_SSL(host, port)
    try:
        imap.login(user, password)
        status, _ = imap.select(folder, readonly=True)
        if status != "OK":
            raise RuntimeError("cannot select mailbox readonly")

        # UID SEARCH — UID стабилен между сессиями (в отличие от sequence number).
        status, data = imap.uid("search", None, "SINCE", since_date)
        if status != "OK":
            raise RuntimeError("IMAP UID search failed")
        uids = data[0].split() if data and data[0] else []

        result = []
        for uid in uids:
            status, raw = imap.uid("fetch", uid, "(RFC822)")
            if status != "OK" or not raw or not raw[0]:
                continue
            raw_bytes = raw[0][1]
            msg = email.message_from_bytes(raw_bytes)
            # Фильтр по Date-заголовку (SINCE имеет дневную гранулярность).
            try:
                dt = parsedate_to_datetime(text_header(msg.get("Date")))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                if dt.astimezone(timezone.utc) < since_dt:
                    continue
            except Exception:
                pass
            parsed_msg = parse_message(raw_bytes, uid.decode(errors="replace"))
            if parsed_msg:
                result.append(parsed_msg)
        return result
    finally:
        try:
            imap.logout()
        except Exception:
            pass
