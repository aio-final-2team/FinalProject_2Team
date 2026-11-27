"""알림장 답장을 문의에 연결하고 준비물 확인 시각을 보관해요."""

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE requests ADD COLUMN source_note_id uuid")
    op.execute("""
        ALTER TABLE requests ADD CONSTRAINT requests_source_note_org_fkey
        FOREIGN KEY (source_note_id,org_id) REFERENCES daily_notes(id,org_id)
    """)
    op.execute("CREATE INDEX requests_source_note_idx ON requests (source_note_id,created_at,id)")
    op.execute("ALTER TABLE daily_notes ADD COLUMN supplies_checked_at timestamptz")


def downgrade():
    op.execute("ALTER TABLE daily_notes DROP COLUMN supplies_checked_at")
    op.execute("DROP INDEX requests_source_note_idx")
    op.execute("ALTER TABLE requests DROP CONSTRAINT requests_source_note_org_fkey")
    op.execute("ALTER TABLE requests DROP COLUMN source_note_id")
