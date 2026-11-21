"""알림 노출 시각을 유지하고 다음 발송 시도를 따로 저장해요."""

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE notifications ADD COLUMN next_attempt_at timestamptz NOT NULL DEFAULT now()")


def downgrade():
    op.execute("ALTER TABLE notifications DROP COLUMN next_attempt_at")
