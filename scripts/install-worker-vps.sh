#!/usr/bin/env bash
# Установка воркера разбора звонков на чистый сервер Ubuntu 24.04 (RU-VPS).
#
# Предполагается, что код репозитория уже лежит на сервере (например, /opt/zcminiapp),
# а рядом заполнен .env.worker. Скрипт ставит Docker, включает firewall и поднимает
# контейнер с автозапуском при перезагрузке.
#
# Запуск на сервере:  sudo bash scripts/install-worker-vps.sh
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "==> Директория проекта: $APP_DIR"

if [[ ! -f .env.worker ]]; then
  echo "ОШИБКА: нет файла .env.worker — скопируйте .env.worker.example и заполните значения." >&2
  exit 1
fi

echo "==> Базовые пакеты"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git ufw fail2ban >/dev/null

if ! command -v docker >/dev/null 2>&1; then
  echo "==> Установка Docker"
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker >/dev/null 2>&1 || true

echo "==> Firewall: SSH открыт, остальное закрыто"
ufw allow OpenSSH >/dev/null 2>&1 || ufw allow 22/tcp >/dev/null 2>&1 || true
ufw --force enable >/dev/null 2>&1 || true

if ! systemctl is-active --quiet fail2ban; then
  systemctl enable --now fail2ban >/dev/null 2>&1 || true
fi

echo "==> Запуск контейнера воркера"
docker compose -f docker-compose.worker.yml up -d --build

sleep 8
echo "==> Состояние:"
docker compose -f docker-compose.worker.yml ps
echo
echo "==> Ответ /status:"
curl -s --max-time 10 http://127.0.0.1:8081/status || echo "(пока нет ответа — смотрите логи)"
echo
echo "Готово. Логи:  docker compose -f docker-compose.worker.yml logs -f --tail=50"
