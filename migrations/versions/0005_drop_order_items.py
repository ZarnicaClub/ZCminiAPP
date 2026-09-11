"""drop order_items (решение заказчика: позиции не нужны)"""
from alembic import op
import sqlalchemy as sa

revision = "0005_drop_order_items"
down_revision = "0004_mp3_hash_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("order_items")


def downgrade() -> None:
    # Восстанавливаем только структуру (данные намеренно не возвращаются).
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
