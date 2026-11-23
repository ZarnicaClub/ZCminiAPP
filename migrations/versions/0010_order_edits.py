"""order_edits: журнал ручных правок заказов из мини-аппа.

Кто, когда и что изменил: без журнала через месяц никто не скажет, кто
сдвинул дату игры. Пишется только на пишущих адресах (сейчас — дата игры).
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_order_edits"
down_revision = "0009_editor_rights"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_edits",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("order_id", sa.Text(), nullable=False),
        sa.Column("field", sa.Text(), nullable=False, server_default="order_date"),
        sa.Column("old_value", sa.Text()),
        sa.Column("new_value", sa.Text()),
        sa.Column("edited_by", sa.BigInteger()),
        sa.Column(
            "edited_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_order_edits_order_id", "order_edits", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_order_edits_order_id", table_name="order_edits")
    op.drop_table("order_edits")
