"""교직원 개인 알림 시간을 저장해요."""

from alembic import op

revision = "0020"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE user_settings (
            user_id uuid PRIMARY KEY,
            org_id uuid NOT NULL,
            quiet_start time,
            quiet_end time,
            updated_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (user_id, org_id) REFERENCES users(id, org_id)
        )
    """)


def downgrade():
    op.drop_table("user_settings")
