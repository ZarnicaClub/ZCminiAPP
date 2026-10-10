# calls-tagger: расшифровка новых звонков и разметка по словам

Служба рядом с `calls_worker`: воркер забирает записи из почты, а `calls_tagger`
берёт **новые** звонки, расшифровывает запись и проставляет теги.

## Что кладём и куда

Ничего нового не создаём: всё пишется в уже существующее поле `calls.metadata` (jsonb).

```json
{
  "tags": {
    "type": "корпоратив",
    "why": "корпоратив",
    "date": {"date": "2026-10-31", "kind": "explicit", "text": "31 октября"},
    "players": {"players": 30, "text": "30 человек"},
    "source": "rules-v1",
    "model": "whisper-small-int8",
    "tagged_at": "2026-10-10T16:20:00+00:00"
  },
  "transcript": "текст разговора одной строкой",
  "transcript_model": "whisper-small-int8"
}
```

Тип запроса: `детский`, `школьная_группа`, `корпоратив`, `праздник_взрослые`,
`просто_игра`, `нецелевой`, `непонятно`. Порядок проверки — от явного к общему:
нецелевое → школа → дети → корпоратив → взрослый праздник → просто игра → `непонятно`.
Правила лежат в `calls_tagger/tags.py` (чистые функции, покрыты `tests/test_calls_tagger.py`).

## Почему только правила

Расшифровка приходит с ошибками («пиньболг» вместо «пейнтбол», «позаналы от платы»),
поэтому ищем **корни** слов, а не точные формы. Правила объяснимы: в `tags.why` видно,
по какой фразе приняли решение. Модель решений (Jev/Laya) — следующий шаг, когда
накопится разметка для проверки.

Ловушки, на которых правила уже спотыкались (закрыты тестами):
«дет» внутри «будет», «класс» внутри «классные перчатки», «в среднем» как будто среда,
«сегодня вам перезвоню» как дата игры, цена «3000 рублей с человека» как число игроков.

## Что берём в работу

`TAGGER_LOOKBACK_HOURS` (на сервере — 24) — окно по `call_datetime`. Архив не переразмечается,
старые теги не переписываются: берём только записи без `metadata.tags`.

## Установка на сервере (Beget, 159.194.225.230)

```bash
python3 -m venv /opt/zcminiapp/.venv-tagger
/opt/zcminiapp/.venv-tagger/bin/pip install -r requirements-tagger.txt
# модель кладём в /opt/zcminiapp/models (качается с HuggingFace при первом запуске)
```

Служба — `systemd`, unit `zc-tagger` (образец — в логе деплоя 13.13 и в `/etc/systemd/system/`):
`EnvironmentFile=/opt/zcminiapp/.env.worker`, `ExecStart=/opt/zcminiapp/.venv-tagger/bin/python -m calls_tagger.main`,
`Restart=always`, `MemoryMax=1300M` (чтобы неудачная расшифровка не утащила за собой воркер).
Переменные: `TAGGER_MODEL=small`, `TAGGER_MODEL_DIR=/opt/zcminiapp/models`,
`TAGGER_HEALTH_PORT=8082`, `TAGGER_INTERVAL_SECONDS=300`, `TAGGER_LOOKBACK_HOURS=24`.

## Эксплуатация

```bash
systemctl status zc-tagger
journalctl -u zc-tagger -n 30
curl -s localhost:8082/status          # selected / tagged / errors / last
/opt/zcminiapp/.venv-tagger/bin/python -m calls_tagger.main --once            # разовый прогон
/opt/zcminiapp/.venv-tagger/bin/python -m calls_tagger.main --once --dry-run  # без записи в базу
```

## Замеры (09–10.10.2026, 2 CPU)

Расшифровка записи 174 с занимает 40–48 с (≈4× реального времени), пик памяти процесса —
684 МБ на модели `small`, 580 МБ на `base`; сама модель на диске — 464 МБ (`small`).
В день приходит 3–13 звонков (≈15 минут аудио) — это 3–4 минуты процессора.
Из-за памяти служба не влезает на VPS 1 ГБ: нужен сервер от 2 ГБ (Prime 2/2, 810 ₽/мес).
