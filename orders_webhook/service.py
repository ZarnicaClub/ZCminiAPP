"""orders-webhook: бизнес-логика приёма заказа (upsert clients + orders)."""
import json
import logging

from psycopg.errors import UndefinedColumn

from shared.contracts import BsoIn, OrderIn
from shared.db import pool
from shared.mailer import is_paid, send_confirmation, smtp_enabled

log = logging.getLogger("orders_webhook.service")


def _claim_confirmation(order_id: str) -> bool:
    """Атомарно занимает отправку письма: True — отправляем мы.

    Флаг — orders.confirmation_sent_at (миграция 0007). Занимаем его ДО отправки,
    поэтому повторный webhook Tilda письмо не дублирует. Если колонки нет
    (миграция не применена) — письмо всё равно отправляем: отсутствие флага не
    должно молча выключать уведомления (так было в v12.15).
    """
    try:
        with pool().connection() as conn:
            row = conn.execute(
                """
                UPDATE orders SET confirmation_sent_at = now()
                WHERE order_id = %s AND confirmation_sent_at IS NULL
                RETURNING 1
                """,
                (order_id,),
            ).fetchone()
            conn.commit()
    except UndefinedColumn:
        log.warning(
            "orders.confirmation_sent_at отсутствует (миграция 0007 не применена) — "
            "идемпотентность писем отключена: order=%s", order_id,
        )
        return True
    return row is not None


def _release_confirmation(order_id: str) -> None:
    """Снимает флаг, если письмо отправить не удалось: даём шанс повторной попытке."""
    try:
        with pool().connection() as conn:
            conn.execute(
                "UPDATE orders SET confirmation_sent_at = NULL WHERE order_id = %s",
                (order_id,),
            )
            conn.commit()
    except Exception:  # noqa: BLE001 — уборка флага не должна ронять отправку
        log.exception("не удалось снять флаг confirmation_sent_at: order=%s", order_id)


def _maybe_send_confirmation(order: OrderIn) -> None:
    """Отправляет подтверждение брони клиенту (email уже есть в orders.customer_email).

    Вызывается ПОСЛЕ ответа Tilda (background-задача, см. upsert_order): SMTP может
    быть медленным или недоступным, и вебхук не должен его ждать — иначе Tilda
    показывает «Произошла ошибка при отправке данных на Webhook URL».

    1 письмо на заказ: флаг занимается атомарно до отправки, а при неудаче
    снимается, чтобы следующая попытка Tilda могла отправить письмо.
    Исключения наружу не пробрасывает: письмо — best-effort побочный эффект,
    заказ к этому моменту уже сохранён.
    """
    try:
        if not is_paid(order) or not order.customer_email or not smtp_enabled():
            return
        if not _claim_confirmation(order.order_id):
            log.info("confirmation already sent, skip: order=%s", order.order_id)
            return
        try:
            send_confirmation(order)
        except Exception:
            _release_confirmation(order.order_id)
            raise
    except Exception:  # noqa: BLE001
        log.exception("email notification error: order=%s", order.order_id)


def upsert_order(order: OrderIn, background=None) -> None:
    """Создаёт/линкует client по телефону и upsert заказа (без order_items).

    background — FastAPI BackgroundTasks: письмо-подтверждение уходит ПОСЛЕ ответа
    Tilda, поэтому недоступный SMTP больше не задерживает вебхук. Без background
    (скрипты, тесты) письмо отправляется синхронно.
    """
    with pool().connection() as conn:
        with conn.cursor() as cur:
            if order.customer_phone:
                cur.execute(
                    """
                    INSERT INTO clients (phone, name, email) VALUES (%s, %s, %s)
                    ON CONFLICT (phone) DO UPDATE SET
                        name = COALESCE(clients.name, EXCLUDED.name),
                        email = COALESCE(clients.email, EXCLUDED.email)
                    """,
                    (order.customer_phone, order.customer_name, order.customer_email),
                )

            cur.execute(
                """
                INSERT INTO orders (
                    order_id, order_status, payment_amount, payment_currency,
                    payment_system, payment_transaction_id, order_date,
                    customer_name, customer_email, customer_phone,
                    game, tent, session_time, qty, extra_fields, raw_payload,
                    received_at, source, client_id
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,
                    now(),'tilda',(SELECT client_id FROM clients WHERE phone=%s)
                )
                ON CONFLICT (order_id) DO UPDATE SET
                    order_status = EXCLUDED.order_status,
                    payment_amount = EXCLUDED.payment_amount,
                    payment_transaction_id = EXCLUDED.payment_transaction_id,
                    order_date = EXCLUDED.order_date,
                    customer_name = EXCLUDED.customer_name,
                    customer_email = EXCLUDED.customer_email,
                    customer_phone = EXCLUDED.customer_phone,
                    game = EXCLUDED.game,
                    tent = EXCLUDED.tent,
                    session_time = EXCLUDED.session_time,
                    qty = EXCLUDED.qty,
                    extra_fields = EXCLUDED.extra_fields,
                    raw_payload = EXCLUDED.raw_payload,
                    client_id = (SELECT client_id FROM clients WHERE phone=%s)
                """,
                (
                    order.order_id, order.order_status, order.payment_amount,
                    order.payment_currency, order.payment_system,
                    order.payment_transaction_id, order.order_date,
                    order.customer_name, order.customer_email, order.customer_phone,
                    order.game, order.tent, order.session_time, order.qty,
                    json.dumps(order.extra_fields, ensure_ascii=False),
                    json.dumps(order.raw_payload, ensure_ascii=False),
                    order.customer_phone, order.customer_phone,
                ),
            )

            # Привязать существующие «бесхозные» звонки к клиенту по телефону.
            if order.customer_phone:
                cur.execute(
                    """
                    UPDATE calls
                    SET client_id = (SELECT client_id FROM clients WHERE phone = %s)
                    WHERE phone = %s AND client_id IS NULL
                    """,
                    (order.customer_phone, order.customer_phone),
                )
                # Если это единственный заказ на этот телефон — привязать и заказ.
                cur.execute(
                    """
                    UPDATE calls
                    SET order_id = %s, status = 'matched'
                    WHERE phone = %s
                      AND order_id IS NULL
                      AND (SELECT COUNT(*) FROM orders WHERE customer_phone = %s) = 1
                    """,
                    (order.order_id, order.customer_phone, order.customer_phone),
                )
        conn.commit()
    log.info("order saved: %s", order.order_id)
    if background is not None:
        background.add_task(_maybe_send_confirmation, order)
    else:
        _maybe_send_confirmation(order)


def upsert_bso(bso: BsoIn) -> dict:
    """Дополняет существующий Order данными БСО (идемпотентный upsert).

    Если Order с таким order_id отсутствует — ничего не пишем и не создаём
    заказ (возвращаем skipped). Повторная отправка / исправления администратора
    перезаписывают строку по ON CONFLICT (order_id).
    """
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM orders WHERE order_id = %s", (bso.order_id,))
            if cur.fetchone() is None:
                return {"status": "skipped", "reason": "order_not_found"}

            cur.execute(
                """
                INSERT INTO orders_bso (
                    order_id, game_date, order_amount, bso_number,
                    players_fact, customer_name, rest_zone_amount,
                    source, received_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, 'gsheets', now(), now()
                )
                ON CONFLICT (order_id) DO UPDATE SET
                    game_date = EXCLUDED.game_date,
                    order_amount = EXCLUDED.order_amount,
                    bso_number = EXCLUDED.bso_number,
                    players_fact = EXCLUDED.players_fact,
                    customer_name = EXCLUDED.customer_name,
                    rest_zone_amount = EXCLUDED.rest_zone_amount,
                    updated_at = now()
                """,
                (
                    bso.order_id, bso.game_date, bso.order_amount, bso.bso_number,
                    bso.players_fact, bso.customer_name, bso.rest_zone_amount,
                ),
            )
        conn.commit()
    log.info("bso saved: %s", bso.order_id)
    return {"status": "ok"}
