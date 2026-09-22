"""calls-worker — цикл парсинга почты + health-HTTP.

Запуск: python -m calls_worker.main
Health-сервер на WORKER_HEALTH_PORT (для healthcheck и внешнего мониторинга).
"""
import json
import logging
import os
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

from calls_worker.service import STATUS, run_once
from shared.logging_config import setup_logging

log = logging.getLogger("calls_worker.main")

# ВАЖНО: `or "..."` вместо значения по умолчанию у os.getenv.
# os.getenv подставляет default только если переменной НЕТ; а платформа/compose
# может передать ПУСТУЮ строку — тогда int("") роняет процесс ещё до старта
# (именно так воркер падал на WORKER_HEALTH_PORT).
HEALTH_PORT = int(os.getenv("WORKER_HEALTH_PORT") or "8081")
INTERVAL = int(os.getenv("WORKER_INTERVAL_SECONDS") or "300")
# Не спамить уведомлениями: не чаще одного сообщения об ошибке в этот интервал.
ALERT_EVERY_SECONDS = int(os.getenv("WORKER_ALERT_EVERY_SECONDS") or "3600")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
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
    HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler).serve_forever()


def notify_telegram(text: str) -> None:
    """Сообщение об ошибке в Telegram. Работает, только если заданы токен бота
    и TELEGRAM_ALERT_CHAT_ID — иначе молча ничего не делает."""
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat = os.getenv("TELEGRAM_ALERT_CHAT_ID")
    if not token or not chat:
        return
    try:
        payload = json.dumps({
            "chat_id": chat,
            "text": text[:3500],
            "disable_notification": True,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:  # noqa: BLE001
        log.warning("не удалось отправить уведомление в Telegram: %s", e)


def main():
    setup_logging()

    # Режим разового прогона: `python -m calls_worker.main --once`
    # Нужен, когда цикл запускается внешним расписанием (Планировщик заданий Windows,
    # cron, расписание Hermes), а не собственным бесконечным циклом.
    import sys
    once = "--once" in sys.argv

    log.info(
        "calls-worker запущен%s: интервал %s c, health-порт %s, окно разбора писем %s ч, ящик %s",
        " (разовый прогон)" if once else "",
        INTERVAL, HEALTH_PORT,
        os.getenv("PARSER_LOOKBACK_HOURS") or "24",
        os.getenv("MAIL_USERNAME") or "(не задан)",
    )

    if once:
        try:
            run_once()
            log.info("разовый прогон завершён: писем %s, сохранено %s, без пары %s, ошибок %s",
                     STATUS["processed"], STATUS["inserted"], STATUS["unmatched"], STATUS["errors"])
        except Exception as e:  # noqa: BLE001
            STATUS["errors"] += 1
            STATUS["last_error"] = str(e)
            log.exception("разовый прогон упал: %s", e)
            notify_telegram(f"⚠️ calls-worker: сбой разового прогона\n{type(e).__name__}: {e}")
            raise SystemExit(1)
        return

    threading.Thread(target=_run_health_server, daemon=True).start()

    last_alert = 0.0
    while True:
        started = time.time()
        before = dict(STATUS)
        try:
            run_once()
            log.info(
                "цикл за %.1f с: писем %s, сохранено %s, привязано %s, без пары %s, ошибок цикла %s",
                time.time() - started,
                STATUS["processed"] - before["processed"],
                STATUS["inserted"] - before["inserted"],
                STATUS["matched"] - before["matched"],
                STATUS["unmatched"] - before["unmatched"],
                STATUS["errors"] - before["errors"],
            )
        except Exception as e:  # noqa: BLE001
            STATUS["errors"] += 1
            STATUS["last_error"] = str(e)
            log.exception("цикл упал: %s", e)
            if time.time() - last_alert > ALERT_EVERY_SECONDS:
                last_alert = time.time()
                notify_telegram(f"⚠️ calls-worker: сбой цикла разбора звонков\n{type(e).__name__}: {e}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
