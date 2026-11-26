"""하루 중 기록. 임시 down 0016 — #377 머지 뒤 0017로 바꿀 것."""

from alembic import op

revision = "0018"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE daily_records (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organizations(id),
            classroom_id uuid NOT NULL,
            child_id uuid NOT NULL,
            note_date date NOT NULL,
            body text NOT NULL CHECK (char_length(body) <= 500),
            author_id uuid NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now(),
            deleted_at timestamptz,
            FOREIGN KEY (classroom_id,org_id) REFERENCES classrooms(id,org_id),
            FOREIGN KEY (child_id,org_id) REFERENCES children(id,org_id),
            FOREIGN KEY (author_id,org_id) REFERENCES users(id,org_id)
        )
    """)
    op.execute("""CREATE INDEX daily_records_active_idx
        ON daily_records(org_id,classroom_id,note_date,child_id,created_at,id) WHERE deleted_at IS NULL""")


def downgrade():
    op.drop_table("daily_records")
