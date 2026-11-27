"""보호자가 확인한 돌봄 메모만 다음 작성에 쓰도록 상태를 나눠요."""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = depends_on = None


def upgrade():
    op.execute("ALTER TABLE memories DROP CONSTRAINT memories_kind_check")
    op.execute("ALTER TABLE memories ADD CONSTRAINT memories_kind_check CHECK (kind IN ('rejection_reason','preference','tone','care_note'))")
    op.execute("ALTER TABLE memories ADD COLUMN child_id uuid, ADD COLUMN confirm_status text NOT NULL DEFAULT 'confirmed' CHECK (confirm_status IN ('pending','confirmed','discarded')), ADD COLUMN confirmed_at timestamptz, ADD FOREIGN KEY (child_id,org_id) REFERENCES children(id,org_id)")
    op.execute("ALTER TABLE notifications DROP CONSTRAINT notifications_kind_check")
    op.execute("""ALTER TABLE notifications ADD CONSTRAINT notifications_kind_check CHECK (kind IN ('needs_info', 'new_card', 'urgent_complaint', 'uncertain_complaint',
                                  'director_report', 'on_hold', 'sent_or_booked', 'parent_confirmed',
                                  'completed', 'rejected', 'note_sent',
                                  'slot_hold_expired', 'hold_resumed',
                                  'consultation_ending', 'consultation_delayed', 'care_requested', 'care_confirmed',
                                  'parent_message', 'reassigned', 'consultation_booked', 'note_corrected', 'cancelled', 'care_rejected', 'memory_candidate'))""")


def downgrade():
    # 확인 후보를 구버전에서 무조건 쓰지 않도록 먼저 지워요.
    op.execute("DELETE FROM notifications WHERE kind='memory_candidate'")
    op.execute("DELETE FROM memories WHERE kind='care_note'")
    op.execute("ALTER TABLE notifications DROP CONSTRAINT notifications_kind_check")
    op.execute("""ALTER TABLE notifications ADD CONSTRAINT notifications_kind_check CHECK (kind IN ('needs_info', 'new_card', 'urgent_complaint', 'uncertain_complaint',
                                  'director_report', 'on_hold', 'sent_or_booked', 'parent_confirmed',
                                  'completed', 'rejected', 'note_sent',
                                  'slot_hold_expired', 'hold_resumed',
                                  'consultation_ending', 'consultation_delayed', 'care_requested', 'care_confirmed',
                                  'parent_message', 'reassigned', 'consultation_booked', 'note_corrected', 'cancelled', 'care_rejected'))""")
    op.drop_column("memories", "confirmed_at")
    op.drop_column("memories", "confirm_status")
    op.drop_column("memories", "child_id")
    op.execute("ALTER TABLE memories DROP CONSTRAINT memories_kind_check")
    op.execute("ALTER TABLE memories ADD CONSTRAINT memories_kind_check CHECK (kind IN ('rejection_reason','preference','tone'))")
