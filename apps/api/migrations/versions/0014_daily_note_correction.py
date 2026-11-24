"""보낸 알림장의 정정 판과 마지막 정정 시각을 보관해요."""

from alembic import op

revision = "0014"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE daily_notes ADD COLUMN version integer NOT NULL DEFAULT 1 CHECK (version >= 1)")
    op.execute("ALTER TABLE daily_notes ADD COLUMN corrected_at timestamptz")


def downgrade():
    op.drop_column("daily_notes", "corrected_at")
    op.drop_column("daily_notes", "version")
