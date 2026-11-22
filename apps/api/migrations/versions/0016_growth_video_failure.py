"""[제안][선택] 작업 중 사진 부족 사유를 보존해요."""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE growth_videos ADD COLUMN failure_reason text")


def downgrade():
    op.execute("ALTER TABLE growth_videos DROP COLUMN failure_reason")
