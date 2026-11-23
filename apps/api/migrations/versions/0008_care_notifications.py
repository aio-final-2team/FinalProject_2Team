"""T46 팀 확인 전 초안: 투약·귀가 접수·교직원 확인 알림이에요."""

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

PREVIOUS_KINDS = """'needs_info', 'new_card', 'urgent_complaint', 'uncertain_complaint',
    'director_report', 'on_hold', 'sent_or_booked', 'parent_confirmed', 'completed', 'rejected', 'note_sent',
    'slot_hold_expired', 'hold_resumed', 'consultation_ending', 'consultation_delayed'"""
NEW_KINDS = "'care_requested', 'care_confirmed'"


def upgrade():
    op.execute("ALTER TABLE notifications DROP CONSTRAINT notifications_kind_check")
    op.execute(f"ALTER TABLE notifications ADD CONSTRAINT notifications_kind_check CHECK (kind IN ({PREVIOUS_KINDS}, {NEW_KINDS}))")


def downgrade():
    op.execute(f"DELETE FROM notifications WHERE kind IN ({NEW_KINDS})")
    op.execute("ALTER TABLE notifications DROP CONSTRAINT notifications_kind_check")
    op.execute(f"ALTER TABLE notifications ADD CONSTRAINT notifications_kind_check CHECK (kind IN ({PREVIOUS_KINDS}))")
