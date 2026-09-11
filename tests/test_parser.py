import hashlib
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from calls_worker.parser import extract_attachments, match_status, parse_message


def _build_msg(subject, attachments):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "rec@example.com"
    msg["To"] = "x@example.com"
    for fn, payload in attachments:
        msg.add_attachment(payload, maintype="audio", subtype="mpeg", filename=fn)
    return msg


def test_match_status():
    assert match_status([]) == "unmatched"
    assert match_status(["a"]) == "matched"
    assert match_status(["a", "b"]) == "ambiguous"
    assert match_status(None) == "unmatched"


def test_extract_attachments():
    payload = b"ID3\x00fake-mp3-bytes"
    msg = _build_msg("s", [("call.mp3", payload)])
    atts = extract_attachments(msg)
    assert len(atts) == 1
    assert atts[0]["filename"] == "call.mp3"
    assert atts[0]["sha256"] == hashlib.sha256(payload).hexdigest()


def test_parse_message():
    subject = "Запись разговора 11.08.2026 14:48:01 +79851297771 Мария Коробова"
    msg = _build_msg(subject, [("call.mp3", b"x")])
    m = parse_message(msg.as_bytes(), "uid123")
    assert m is not None
    assert m["email_id"] == "uid123"
    assert m["parsed"]["phone"] == "79851297771"
    assert m["parsed"]["administrator"] == "Мария Коробова"
    assert len(m["attachments"]) == 1


def test_parse_message_invalid():
    msg = _build_msg("Обычное письмо", [("call.mp3", b"x")])
    assert parse_message(msg.as_bytes(), "uid1") is None


if __name__ == "__main__":
    test_match_status()
    test_extract_attachments()
    test_parse_message()
    test_parse_message_invalid()
    print("test_parser: OK")
