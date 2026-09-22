# Воркер разбора звонков на отдельном российском VPS

## Что это

`calls_worker` — фоновый цикл (не HTTP-сервис): каждые 5 минут читает письма с записями
звонков из ящика Яндекса по IMAP, вытаскивает MP3, считает хэш, кладёт файл в S3 и
привязывает звонок к заказу по номеру телефона.

Раньше он жил третьим сервисом в стеке App Platform. Теперь у него отдельный сервер —
по двум причинам:

1. В App Platform он был самым дорогим инстансом (2 ГБ / 810 ₽) при потребности в 1 ГБ.
2. Пока он был вторым контейнером compose-стека, платформа теряла ~половину входящих
   соединений к веб-приложению: обычные приложения (одно на инстанс) отвечают 100 %,
   compose-стек — нет. Оставшись без воркера, веб-приложение вернётся в обычный режим.

## Что нужно один раз

1. VPS в РФ: Ubuntu 24.04, 2 vCPU / 4 ГБ RAM / 40+ ГБ NVMe (Beget ~460 ₽/мес,
   Selectel VDS 2-4-50 ~700 ₽/мес, Timeweb Cloud-50 ~1000 ₽/мес).
2. При создании добавить SSH-ключ (публичная часть — `secrets/ru-vps_ed25519.pub`
   на сервере Hermes, отпечаток `SHA256:zh5Ceo6kO0PmV3DmB4pGGeNEZyDDBnKRq8sZXh5OAps`).

## Установка

```bash
# код на сервер (с машины Hermes):
rsync -az --exclude .git /opt/data/zcminiapp/ root@<IP>:/opt/zcminiapp/

# на сервере:
cd /opt/zcminiapp
cp .env.worker.example .env.worker
nano .env.worker          # DATABASE_URL, S3_*, MAIL_*, при желании TELEGRAM_*
bash scripts/install-worker-vps.sh
```

Скрипт ставит Docker, включает ufw (открыт только SSH) и fail2ban, поднимает контейнер
с `restart: unless-stopped` (переживает перезагрузку сервера).

## Эксплуатация

```bash
docker compose -f docker-compose.worker.yml logs -f --tail=50   # логи
docker compose -f docker-compose.worker.yml ps                  # состояние
curl -s localhost:8081/status                                   # счётчики цикла
docker compose -f docker-compose.worker.yml up -d --build       # обновить код
```

`/status` отдаёт: `last_cycle_at`, `processed`, `inserted`, `matched`, `unmatched`,
`errors`, `last_error`. Порт слушается только на localhost — наружу не публикуется.

## Если сервер простаивал

Письма остаются в ящике, поэтому пропущенное обработается при следующем запуске —
в пределах окна `PARSER_LOOKBACK_HOURS` (в примере 72 часа). Дубли отсекаются по UID
письма и хэшу MP3, так что окно можно смело увеличивать.

## Уведомления о сбоях

Если задать `TELEGRAM_BOT_TOKEN` и `TELEGRAM_ALERT_CHAT_ID`, воркер при падении цикла
пришлёт сообщение (не чаще одного раза в час).
