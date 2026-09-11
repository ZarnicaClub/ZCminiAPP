"""create clients"""
from alembic import op
import sqlalchemy as sa

revision = "0002_clients"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clients",
        sa.Column("client_id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("name", sa.Text()),
        sa.Column("email", sa.Text()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("phone", name="clients_phone_key"),
    )


def downgrade() -> None:
    op.drop_table("clients")
