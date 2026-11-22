"""아이별 진행 중인 성장 영상은 하나만 허용해요."""

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        WITH ranked AS (
            SELECT id,row_number() OVER (PARTITION BY child_id ORDER BY created_at DESC,id DESC) AS n
            FROM growth_videos WHERE status IN ('queued','running') AND deleted_at IS NULL
        )
        UPDATE growth_videos SET status='failed',completed_at=now()
        WHERE id IN (SELECT id FROM ranked WHERE n>1)
    """)
    op.execute("CREATE UNIQUE INDEX growth_videos_pending_child_idx ON growth_videos(child_id) "
               "WHERE status IN ('queued','running') AND deleted_at IS NULL")


def downgrade():
    op.execute("DROP INDEX growth_videos_pending_child_idx")
