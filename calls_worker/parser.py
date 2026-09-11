"""Парсер письма со звонком: вложения, длительность, матчинг (чистая логика)."""
import io
from email import message_from_bytes
from email.header import decode_header

from shared.s3 import sha256_hex
from shared.subject import parse_subject


def text_header(value) -> str:
    if not value:
        return ""
    out = []
    for raw, enc in decode_header(value):
        if isinstance(raw, bytes):
            charset = enc or "utf-8"
            try:
                out.append(raw.decode(charset, errors="replace"))
            except (LookupError, UnicodeError):
                out.append(raw.decode("utf-8", errors="replace"))
        else:
            out.append(str(raw))
    return "".join(out)


def extract_attachments(msg):
    """Возвращает список MP3-вложений: [{filename, content_type, payload, sha256}]."""
    out = []
    for part in msg.walk():
        filename = part.get_filename()
        if not filename:
            continue
        filename = text_header(filename)
        payload = part.get_payload(decode=True) or b""
        is_mp3 = (
            part.get_content_type() == "audio/mpeg"
            or filename.lower().endswith(".mp3")
        )
        if is_mp3:
            out.append({
                "filename": filename,
                "content_type": part.get_content_type(),
                "payload": payload,
                "size_bytes": len(payload),
                "sha256": sha256_hex(payload),
            })
    return out


def parse_message(raw_bytes, email_id):
    """Из байтов письма -> dict(email_id, subject, parsed, attachments) или None."""
    msg = message_from_bytes(raw_bytes)
    subject = text_header(msg.get("Subject"))
    parsed = parse_subject(subject)
    if not parsed:
        return None
    return {
        "email_id": email_id,
        "subject": subject,
        "parsed": parsed,
        "attachments": extract_attachments(msg),
    }


def match_status(order_ids) -> str:
    """0 заказов -> unmatched; 1 -> matched; >1 -> ambiguous."""
    n = len(order_ids or [])
    if n == 0:
        return "unmatched"
    if n == 1:
        return "matched"
    return "ambiguous"


def mp3_duration(payload) -> int:
    """Длительность MP3 в секундах (mutagen)."""
    from mutagen.mp3 import MP3

    audio = MP3(io.BytesIO(payload))
    return int(round(float(audio.info.length)))
