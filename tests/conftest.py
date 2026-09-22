"""Конфигурация pytest.

`test_smoke.py` — не обычный юнит-тест, а ручной скрипт-проверка против ЖИВОЙ БД
(он выполняется на уровне модуля и требует DATABASE_URL). В CI базы нет,
поэтому автоматически его не собираем; запускать вручную:
    DATABASE_URL=... python tests/test_smoke.py
"""
collect_ignore = ["test_smoke.py"]
