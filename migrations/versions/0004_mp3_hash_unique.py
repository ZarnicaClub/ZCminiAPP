"""mp3_hash UNIQUE + NOT NULL (выполняется ПОСЛЕ дедупликации данных)"""
from alembic import op

revision = "0004_mp3_hash_unique"
down_revision = "0003_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("calls_mp3_hash_key", "calls", ["mp3_hash"])
    op.alter_column("calls", "mp3_hash", nullable=False)


def downgrade() -> None:
    op.drop_constraint("calls_mp3_hash_key", "calls", type_="unique")
    op.alter_column("calls", "mp3_hash", nullable=True)
