"""Закладка воркера: за цикл качаем только новые письма (вариант A, 29.09.2026).

Проверки без почты и без базы: ящик — двойник imaplib, список «уже разобрано»
и файл закладки подменяются.
"""
import sys
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from calls_worker import imap, state  # noqa: E402
from calls_worker.parser import parse_message  # noqa: E402
from calls_worker.service import process_one  # noqa: E402

SUBJ = "Запись разговора 11.08.2026 14:48:01 +79851297771 Мария Коробова"


def _mail(subject=SUBJ, attachments=(("call.mp3", b"ID3fake-mp3"),)):
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = "rec@example.com"
    msg["Date"] = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    for fn, payload in attachments:
        msg.add_attachment(payload, maintype="audio", subtype="mpeg", filename=fn)
    return msg.as_bytes()


class FakeIMAP:
    """Двойник imaplib.IMAP4_SSL — только то, что использует воркер."""

    def __init__(self, uids, uidvalidity=1, total=None, fail_fetch=(), messages=None):
        self.uids = list(uids)
        self.uidvalidity = uidvalidity
        self.total = len(uids) if total is None else total
        self.fail_fetch = set(fail_fetch)
        self.messages = messages or {}
        self.searches = []
        self.fetched = []
        self.untagged_responses = {}

    def login(self, user, password):
        return "OK", [b"ok"]

    def select(self, folder, readonly=False):
        self.untagged_responses = {
            "EXISTS": [str(self.total).encode()],
            "UIDVALIDITY": [str(self.uidvalidity).encode()],
        }
        return "OK", [str(self.total).encode()]

    def logout(self):
        return "BYE", [b"bye"]

    def uid(self, command, *args):
        if command == "search":
            key, value = args[1], args[2]
            self.searches.append((key, value))
            if key == "UID":
                low = int(value.split(":")[0])
                found = [u for u in self.uids if u >= low]
            else:                      # SINCE — окно по дате, отдаём всё
                found = list(self.uids)
            payload = " ".join(str(u) for u in found).encode()
            return "OK", [payload]
        if command == "fetch":
            uid = int(args[0])
            self.fetched.append(uid)
            if uid in self.fail_fetch:
                raise imap.imaplib.IMAP4.abort("problems with connection")
            return "OK", [(b"1 (RFC822 {0}", self.messages.get(uid, _mail()))]
        raise AssertionError(f"неожиданная команда {command}")


def _run(monkeypatch, fake, known=(), cursor=None):
    """Прогон одного прохода по ящику с подменённым ящиком, базой и файлом закладки."""
    monkeypatch.setenv("MAIL_USERNAME", "u")
    monkeypatch.setenv("MAIL_PASSWORD", "p")
    monkeypatch.setattr(imap.imaplib, "IMAP4_SSL", lambda host, port: fake)
    monkeypatch.setattr(
        imap, "known_email_ids",
        lambda uids: {str(u) for u in uids if str(u) in {str(k) for k in known}},
    )
    monkeypatch.setattr(imap.state, "load", lambda: cursor)
    saved = []
    monkeypatch.setattr(imap.state, "save", lambda last, uv=None: saved.append((last, uv)))
    sel = imap.fetch_new_messages()
    imap.advance_cursor(sel)            # как в цикле: закладка двигается по итогам прохода
    return sel, saved


def test_no_cursor_works_by_window(monkeypatch):
    fake = FakeIMAP([101, 102])
    sel, _ = _run(monkeypatch, fake, cursor=None)
    assert sel.mode == "window"
    assert fake.searches[0][0] == "SINCE"
    assert sel.uids == [101, 102]
    assert fake.fetched == [101, 102]


def test_cursor_asks_only_after_last_uid(monkeypatch):
    fake = FakeIMAP([101, 102, 103], uidvalidity=7)
    sel, _ = _run(monkeypatch, fake, cursor=state.Cursor(last_uid=100, uidvalidity=7))
    assert sel.mode == "cursor"
    assert fake.searches == [("UID", "101:*")]
    assert sel.uids == [101, 102, 103]


def test_already_parsed_letters_are_not_downloaded(monkeypatch):
    """Главное требование: цикл без новых писем = 0 скачиваний."""
    fake = FakeIMAP([101, 102, 103], uidvalidity=1)
    sel, saved = _run(monkeypatch, fake, known={"101", "102", "103"},
                      cursor=state.Cursor(last_uid=100, uidvalidity=1))
    assert sel.to_download == []
    assert fake.fetched == []
    assert sel.skipped_known == 3
    assert saved == [(103, 1)]          # закладка уехала вперёд, качать больше нечего


def test_downloads_only_unknown(monkeypatch):
    fake = FakeIMAP([101, 102, 103], uidvalidity=1)
    sel, _ = _run(monkeypatch, fake, known={"101"},
                  cursor=state.Cursor(last_uid=100, uidvalidity=1))
    assert sel.to_download == [102, 103]
    assert fake.fetched == [102, 103]
    assert len(sel.messages) == 2


def test_uidvalidity_change_drops_cursor(monkeypatch):
    fake = FakeIMAP([101], uidvalidity=2)
    sel, _ = _run(monkeypatch, fake, cursor=state.Cursor(last_uid=100, uidvalidity=1))
    assert sel.mode == "window"
    assert fake.searches[0][0] == "SINCE"


def test_failed_download_holds_cursor(monkeypatch):
    """Сбой скачивания — письмо повторяем: закладка за него не проходит."""
    fake = FakeIMAP([101, 102, 103], uidvalidity=1, fail_fetch=[102])
    sel, saved = _run(monkeypatch, fake, cursor=state.Cursor(last_uid=100, uidvalidity=1))
    assert sel.failed == [102]
    assert saved == [(101, 1)]


def test_cursor_never_moves_backwards(monkeypatch):
    fake = FakeIMAP([150], uidvalidity=1)
    sel, saved = _run(monkeypatch, fake, cursor=state.Cursor(last_uid=200, uidvalidity=1))
    assert sel.uids == []               # сервер отдал письмо ниже закладки — отсекли
    assert saved == []


def test_no_new_mail_does_not_touch_cursor_file(monkeypatch):
    fake = FakeIMAP([], uidvalidity=1)
    sel, saved = _run(monkeypatch, fake, cursor=state.Cursor(last_uid=150, uidvalidity=1))
    assert sel.uids == []
    assert saved == []


def test_mail_without_mp3_passes_cursor(monkeypatch):
    """Письмо без MP3 в базу не пишется — закладка должна его пропустить."""
    fake = FakeIMAP([101], uidvalidity=1, messages={101: _mail(attachments=())})
    sel, saved = _run(monkeypatch, fake, cursor=state.Cursor(last_uid=100, uidvalidity=1))
    assert sel.failed == []
    assert saved == [(101, 1)]
    rec = process_one(sel.messages[0], None, None, set(), set())
    assert rec["action"] == "malformed"
    assert rec["status"] is None


def test_mail_with_two_mp3_passes_cursor(monkeypatch):
    attachments = (("a.mp3", b"ID3a"), ("b.mp3", b"ID3b"))
    fake = FakeIMAP([101], uidvalidity=1, messages={101: _mail(attachments=attachments)})
    sel, _ = _run(monkeypatch, fake, cursor=state.Cursor(last_uid=100, uidvalidity=1))
    rec = process_one(sel.messages[0], None, None, set(), set())
    assert rec["action"] == "malformed"


def test_duplicate_is_not_counted_as_unmatched(monkeypatch):
    parsed = parse_message(_mail(), "101")
    rec = process_one(parsed, None, None, {"101"}, set())
    assert rec["action"] == "skipped_duplicate"
    assert rec["status"] is None        # «без пары» от дублей больше не растёт


def test_broken_mp3_does_not_hold_cursor(monkeypatch):
    """Битый MP3 — постоянная причина: закладка идёт дальше, вечных повторов нет."""
    fake = FakeIMAP([101], uidvalidity=1,
                    messages={101: _mail(attachments=(("call.mp3", b"not-an-mp3"),))})
    sel, saved = _run(monkeypatch, fake, cursor=state.Cursor(last_uid=100, uidvalidity=1))
    rec = process_one(sel.messages[0], None, None, set(), set())
    assert rec["action"] == "error" and rec["status"] is None
    assert sel.failed == []
    assert saved == [(101, 1)]


def test_state_file_roundtrip(monkeypatch, tmp_path):
    path = tmp_path / "cursor.json"
    monkeypatch.setenv("WORKER_STATE_FILE", str(path))
    assert state.load() is None                     # файла нет — работаем по окну
    state.save(14848, 741325)
    cur = state.load()
    assert cur.last_uid == 14848 and cur.uidvalidity == 741325
    assert cur.updated_at is not None

    path.write_text("{ это не JSON", encoding="utf-8")
    assert state.load() is None                     # битый файл не роняет цикл


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
