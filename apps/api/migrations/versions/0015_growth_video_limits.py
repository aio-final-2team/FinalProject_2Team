"""아이별 진행 중인 성장 영상은 하나만 허용해요."""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("CREATE UNIQUE INDEX growth_videos_pending_child_idx ON growth_videos(child_id) "
               "WHERE status IN ('queued','running') AND deleted_at IS NULL")


def downgrade():
    op.execute("DROP INDEX growth_videos_pending_child_idx")
