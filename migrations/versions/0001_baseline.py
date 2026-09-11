"""baseline: legacy schema (orders, order_items, calls)

Соответствует DDL из data/default_db.sql (PostgreSQL 17.10).
На production таблицы уже существуют -> `alembic stamp 0001_baseline`.
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("order_status", sa.Text()),
        sa.Column("payment_amount", sa.Numeric(12, 2)),
        sa.Column("payment_currency", sa.Text(), server_default="RUB"),
        sa.Column("payment_system", sa.Text()),
        sa.Column("payment_transaction_id", sa.Text()),
        sa.Column("order_date", sa.Date()),
        sa.Column("customer_name", sa.Text()),
        sa.Column("customer_email", sa.Text()),
        sa.Column("customer_phone", sa.Text()),
        sa.Column("game", sa.Text()),
        sa.Column("tent", sa.Text()),
        sa.Column("session_time", sa.Text()),
        sa.Column("qty", sa.Text()),
        sa.Column("extra_fields", sa.dialects.postgresql.JSONB()),
        sa.Column("raw_payload", sa.dialects.postgresql.JSONB()),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("order_id", name="orders_order_id_key"),
    )
    op.create_index("idx_orders_game", "orders", ["game"])
    op.create_index("idx_orders_order_status", "orders", ["order_status"])

    op.create_table(
        "order_items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("product_name", sa.Text()),
        sa.Column("price", sa.Numeric(12, 2)),
        sa.Column("quantity", sa.Integer()),
        sa.Column("amount", sa.Numeric(12, 2)),
        sa.Column("extra", sa.dialects.postgresql.JSONB()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.order_id"],
            ondelete="CASCADE", name="order_items_order_id_fkey",
        ),
    )
    op.create_index("idx_order_items_order_id", "order_items", ["order_id"])

    op.create_table(
        "calls",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("email_id", sa.Text(), nullable=False),
        sa.Column("order_id", sa.Text()),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("call_datetime", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("administrator", sa.Text()),
        sa.Column("mp3_filename", sa.Text()),
        sa.Column("s3_key", sa.Text()),
        sa.Column("duration_seconds", sa.Integer()),
        sa.Column("status", sa.Text(), nullable=False, server_default="unmatched"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadata", sa.dialects.postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.UniqueConstraint("email_id", name="calls_email_id_key"),
        sa.CheckConstraint(
            "status IN ('matched','unmatched','ambiguous')",
            name="calls_status_check",
        ),
    )
    op.create_index("idx_calls_call_datetime", "calls", ["call_datetime"])
    op.create_index("idx_calls_order_id", "calls", ["order_id"])
    op.create_index("idx_calls_phone", "calls", ["phone"])
    op.create_index("idx_calls_status", "calls", ["status"])


def downgrade() -> None:
    op.drop_table("calls")
    op.drop_table("order_items")
    op.drop_table("orders")
