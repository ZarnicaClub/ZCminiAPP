"""add client links + mp3_hash (nullable; unique добавляется после дедупа)"""
from alembic import op
import sqlalchemy as sa

revision = "0003_links"
down_revision = "0002_clients"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("client_id", sa.BigInteger()))
    op.add_column("orders", sa.Column("source", sa.Text(), nullable=False, server_default="tilda"))
    op.create_foreign_key("orders_client_id_fkey", "orders", "clients", ["client_id"], ["client_id"])
    op.create_index("idx_orders_client_id", "orders", ["client_id"])

    op.add_column("calls", sa.Column("client_id", sa.BigInteger()))
    op.add_column("calls", sa.Column("mp3_hash", sa.Text()))
    op.create_foreign_key("calls_client_id_fkey", "calls", "clients", ["client_id"], ["client_id"])
    op.create_index("idx_calls_client_id", "calls", ["client_id"])
    op.create_index("idx_calls_mp3_hash", "calls", ["mp3_hash"])


def downgrade() -> None:
    op.drop_constraint("calls_client_id_fkey", "calls", type_="foreignkey")
    op.drop_index("idx_calls_mp3_hash", table_name="calls")
    op.drop_index("idx_calls_client_id", table_name="calls")
    op.drop_column("calls", "mp3_hash")
    op.drop_column("calls", "client_id")

    op.drop_constraint("orders_client_id_fkey", "orders", type_="foreignkey")
    op.drop_index("idx_orders_client_id", table_name="orders")
    op.drop_column("orders", "source")
    op.drop_column("orders", "client_id")
