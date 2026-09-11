"""add orders.confirmation_sent_at (защита от повторной отправки email-уведомления)

Идемпотентность отправки подтверждения брони: флаг-колонка в существующей таблице
orders. NULL = письмо ещё не отправлено; NOT NULL = отправлено. Отдельная таблица не нужна.
"""
from alembic import op
import sqlalchemy as sa

revision = "0007_confirmation_sent_at"
down_revision = "0006_orders_bso"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("confirmation_sent_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "confirmation_sent_at")
