"""Проверки зависимостей для /healthz."""
import logging

log = logging.getLogger("shared.health")


def check_db() -> bool:
    try:
        from .db import pool
        with pool().connection() as conn:
            conn.execute("SELECT 1")
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("db check failed: %s", e)
        return False


def check_s3() -> bool:
    try:
        from .s3 import s3_client
        client, bucket = s3_client()
        client.head_bucket(Bucket=bucket)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("s3 check failed: %s", e)
        return False
