"""create orders_bso (БСО из Google Sheets)

Один БСО на один заказ: unique по order_id, FK на orders.order_id (CASCADE).
Данные приходят из Google Sheets (лист БАЛАНС, статья Касса) и дополняют
существующий Order — новый заказ из этой таблицы не создаётся.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_orders_bso"
down_revision = "0005_drop_order_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orders_bso",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("game_date", sa.Date()),
        sa.Column("order_amount", sa.Numeric(12, 2)),
        sa.Column("bso_number", sa.Text()),
        sa.Column("players_fact", sa.Integer()),
        sa.Column("customer_name", sa.Text()),
        sa.Column("rest_zone_amount", sa.Numeric(12, 2)),
        sa.Column("source", sa.Text(), nullable=False, server_default="gsheets"),
        sa.Column("received_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(
            ["order_id"], ["orders.order_id"],
            ondelete="CASCADE", name="orders_bso_order_id_fkey",
        ),
        sa.UniqueConstraint("order_id", name="orders_bso_order_id_key"),
    )
    op.create_index("idx_orders_bso_order_id", "orders_bso", ["order_id"])
    op.create_index("idx_orders_bso_bso_number", "orders_bso", ["bso_number"])
    op.create_index("idx_orders_bso_game_date", "orders_bso", ["game_date"])


def downgrade() -> None:
    op.drop_index("idx_orders_bso_game_date", table_name="orders_bso")
    op.drop_index("idx_orders_bso_bso_number", table_name="orders_bso")
    op.drop_index("idx_orders_bso_order_id", table_name="orders_bso")
    op.drop_table("orders_bso")
