"""crm_editors: белый список Telegram-ID, кому можно вносить правки в CRM.

Закрыто по умолчанию: нет строки в таблице (или is_active = false) — писать
нельзя, чтение не меняется. Проверка только на сервере, по ``user.id`` из
подписанного initData.

ВАЖНО про накат в боевой базе: метка ``alembic_version`` стоит на
``0006_orders_bso``, хотя колонка ``orders.confirmation_sent_at`` (0007) уже
существует. Перед upgrade нужно ``alembic stamp 0007_confirmation_sent_at``,
иначе 0007 упадёт на повторном ADD COLUMN. Миграция 0008 (терминал БСО) —
локальная ветка, в git её нет; поэтому эта миграция продолжает 0007.
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_editor_rights"
down_revision = "0007_confirmation_sent_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "crm_editors",
        sa.Column("telegram_id", sa.BigInteger(), primary_key=True),
        sa.Column("display_name", sa.Text()),
        sa.Column("username", sa.Text()),
        # admin — правит и управляет списком; editor — только вносит правки
        sa.Column("role", sa.Text(), nullable=False, server_default="editor"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("added_by", sa.BigInteger()),
        sa.Column(
            "added_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_table("crm_editors")
