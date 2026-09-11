"""Пул соединений PostgreSQL (psycopg_pool), ленивый синглтон."""
import os

_pool = None


def pool():
    """Возвращает общий ConnectionPool (создаёт при первом обращении)."""
    global _pool
    if _pool is None:
        from psycopg_pool import ConnectionPool

        url = os.environ.get("DATABASE_URL")
        if not url:
            raise RuntimeError("DATABASE_URL не задан")
        # Ограниченный пул: каждый сервис держит 1..5 соединений.
        _pool = ConnectionPool(
            url,
            min_size=1,
            max_size=5,
            max_idle=240,
            check=ConnectionPool.check_connection,
        )
    return _pool


def close_pool():
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
