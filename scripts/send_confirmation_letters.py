"""Разовая рассылка писем-подтверждений по уже оплаченным заказам.

Зачем: письма не уходили из-за закрытых почтовых портов (SMTP), у всех старых заказов
`orders.confirmation_sent_at` пуст. Этим скриптом отправляем подтверждения выборочно —
только по указанным заказам (или по списку дат), НЕ по всей базе.

Запуск (по умолчанию — только показать, что будет отправлено):
    python scripts/send_confirmation_letters.py --orders 1154277982 1035564872
    python scripts/send_confirmation_letters.py --dates 2026-09-29 2026-10-03
    python scripts/send_confirmation_letters.py --dates 2026-10-03 --yes     # реальная отправка

Поведение:
- без флага --yes ничего не отправляет и не меняет в базе (dry-run);
- берёт только оплаченные заказы с email, у которых `confirmation_sent_at` пуст
  (письмо не уйдёт дважды);
- флаг `confirmation_sent_at` ставится ТОЛЬКО после успешного ответа Postbox —
  если отправка упала, заказ остаётся без отметки и его можно повторить;
- ключи читаются из окружения (`POSTBOX_KEY_ID`/`POSTBOX_SECRET`), адрес отправителя
  и шаблон — из shared/mailer.py.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared import mailer  # noqa: E402
from shared.contracts import OrderIn  # noqa: E402
from shared.db import pool  # noqa: E402

SELECT = """
    select order_id, order_status, payment_amount, payment_transaction_id, order_date,
           customer_name, customer_email, game, tent, session_time, qty, raw_payload
    from orders
    where order_status = 'paid'
      and customer_email is not null and customer_email <> ''
      and confirmation_sent_at is null
      and ({where})
    order by order_date, order_id
"""


def fetch(args) -> list[dict]:
    if args.orders:
        where, params = "order_id = any(%s)", (args.orders,)
    else:
        where, params = "order_date = any(%s)", (args.dates,)
    with pool().connection() as conn:
        with conn.cursor() as cur:
            cur.execute(SELECT.format(where=where), params)
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]


def mark_sent(order_id: str) -> None:
    """Ставим отметку после успешной отправки (атомарно, только если её ещё нет)."""
    with pool().connection() as conn:
        conn.execute(
            "UPDATE orders SET confirmation_sent_at = now() "
            "WHERE order_id = %s AND confirmation_sent_at IS NULL",
            (order_id,),
        )
        conn.commit()


def to_order(row: dict) -> OrderIn:
    return OrderIn(
        order_id=row["order_id"],
        order_status=row["order_status"],
        payment_amount=float(row["payment_amount"]) if row["payment_amount"] is not None else None,
        payment_transaction_id=row["payment_transaction_id"],
        order_date=str(row["order_date"]) if row["order_date"] else None,
        customer_name=row["customer_name"],
        customer_email=row["customer_email"],
        game=row["game"],
        tent=row["tent"],
        session_time=row["session_time"],
        qty=row["qty"],
        raw_payload=row["raw_payload"] or {},
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Рассылка писем-подтверждений по заказам")
    p.add_argument("--orders", nargs="*", help="номера заказов (order_id)")
    p.add_argument("--dates", nargs="*", help="даты заказов, ISO (2026-10-03)")
    p.add_argument("--yes", action="store_true", help="реально отправлять (иначе только показать)")
    args = p.parse_args()
    if not args.orders and not args.dates:
        p.error("укажите --orders или --dates")

    rows = fetch(args)
    print(f"отправка включена: {mailer.email_enabled()} | отправитель: {mailer.FROM_EMAIL}")
    print(f"к отправке подходят {len(rows)} заказ(ов)\n")
    if not rows:
        return 0

    sent, failed = [], []
    for row in rows:
        order = to_order(row)
        print(f"  №{order.order_id} | {row['order_date']} | {order.customer_name} | {order.customer_email} | "
              f"{order.qty} чел | {order.payment_amount} ₽", end="")
        if not args.yes:
            print("  → dry-run, не отправляю")
            continue
        try:
            status = mailer.send_confirmation(order)
            mark_sent(order.order_id)
            sent.append(order.order_id)
            print(f"  → отправлено ({status})")
        except Exception as exc:  # noqa: BLE001
            failed.append(order.order_id)
            print(f"  → ОШИБКА: {str(exc).split('RequestID')[0].strip()[:160]}")
        sys.stdout.flush()

    if args.yes:
        print(f"\nитог: отправлено {len(sent)}, ошибок {len(failed)}"
              + (f" | не ушло: {', '.join(failed)}" if failed else ""))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
