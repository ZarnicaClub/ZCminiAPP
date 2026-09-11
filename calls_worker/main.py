"""calls-worker — цикл парсинга почты + health-HTTP.

Запуск: python -m calls_worker.main
Health-сервер на WORKER_HEALTH_PORT (для healthcheck App Platform).
"""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from calls_worker.service import STATUS, run_once

HEALTH_PORT = int(os.getenv("WORKER_HEALTH_PORT", "8081"))
INTERVAL = int(os.getenv("WORKER_INTERVAL_SECONDS", "300"))


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/healthz", "/status"):
            body = json.dumps(STATUS).encode("utf-8")
            self.send_response(200)
        else:
            body = b'{"error":"not_found"}'
            self.send_response(404)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # подавляем access-лог
        pass


def _run_health_server():
    HTTPServer(("0.0.0.0", HEALTH_PORT), HealthHandler).serve_forever()


def main():
    threading.Thread(target=_run_health_server, daemon=True).start()
    while True:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001
            STATUS["errors"] += 1
            STATUS["last_error"] = str(e)
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
