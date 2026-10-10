"""calls-tagger — разметка новых звонков: цикл + health-HTTP.

Запуск: python -m calls_tagger.main [--once] [--dry-run]
Health: http://127.0.0.1:TAGGER_HEALTH_PORT/status

Отдельная служба (`zc-tagger`) рядом с воркером: расшифровка тяжёлая, и её падение
не должно задевать приём звонков из почты.
"""
import json
import logging
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from calls_tagger.service import STATUS, run_once
from shared.logging_config import setup_logging

log = logging.getLogger("calls_tagger.main")

# `or "..."` — платформа/compose может передать ПУСТУЮ строку, а int("") роняет процесс.
HEALTH_PORT = int(os.getenv("TAGGER_HEALTH_PORT") or "8082")
INTERVAL = int(os.getenv("TAGGER_INTERVAL_SECONDS") or "300")
ALERT_EVERY_SECONDS = int(os.getenv("TAGGER_ALERT_EVERY_SECONDS") or "3600")
LOOKBACK_HOURS = os.getenv("TAGGER_LOOKBACK_HOURS") or "72"


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path in ("/healthz", "/status"):
            body = json.dumps(STATUS, ensure_ascii=False, default=str).encode("utf-8")
            self.send_response(200)
        else:
            body = b'{"error":"not_found"}'
            self.send_response(404)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # подавляем access-лог
        pass


def _run_health_server():
    HTTPServer(("127.0.0.1", HEALTH_PORT), HealthHandler).serve_forever()


def notify_telegram(text: str) -> None:
    """Уведомление об ошибке — только если заданы бот и чат, иначе молча ничего."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_ALERT_CHAT_ID")
    if not token or not chat:
        return
    try:
        payload = json.dumps({"chat_id": chat, "text": text[:3500],
                              "disable_notification": True}).encode("utf-8")
        req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                     data=payload, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:  # noqa: BLE001
        log.warning("не удалось отправить уведомление в Telegram: %s", e)


def main():
    setup_logging()
    once = "--once" in sys.argv
    dry_run = "--dry-run" in sys.argv

    log.info(
        "calls-tagger запущен%s%s: интервал %s c, health-порт %s, окно разметки %s ч, модель %s",
        " (разовый прогон)" if once else "", " (без записи)" if dry_run else "",
        INTERVAL, HEALTH_PORT, LOOKBACK_HOURS, os.getenv("TAGGER_MODEL") or "small",
    )

    if once:
        try:
            run_once(dry_run=dry_run)
            log.info("разовый прогон завершён: к обработке %s, размечено %s, ошибок %s",
                     STATUS["selected"], STATUS["tagged"], STATUS["errors"])
        except Exception as e:  # noqa: BLE001
            STATUS["errors"] += 1
            STATUS["last_error"] = str(e)
            log.exception("разовый прогон упал: %s", e)
            notify_telegram(f"⚠️ calls-tagger: сбой разового прогона\n{type(e).__name__}: {e}")
            raise SystemExit(1)
        return

    threading.Thread(target=_run_health_server, daemon=True).start()

    last_alert = 0.0
    while True:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001
            STATUS["errors"] += 1
            STATUS["last_error"] = str(e)
            log.exception("цикл упал: %s", e)
            if time.time() - last_alert > ALERT_EVERY_SECONDS:
                last_alert = time.time()
                notify_telegram(f"⚠️ calls-tagger: сбой цикла разметки звонков\n{type(e).__name__}: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
