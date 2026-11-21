"""상담 지연 기록과 종료·대체 시간 알림을 더해요."""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

PREVIOUS_ACTIONS = """'created', 'classified', 'info_requested', 'assigned',
                                   'reassigned', 'drafted', 'checked', 'returned',
                                   'approved', 'rejected', 'held', 'resumed', 'escalated', 'instructed',
                                   'sent', 'booked', 'completed', 'tool_called',
                                   'tool_failed', 'permission_denied',
                                   'parent_confirmed', 'risk_reclassified', 'dismissed',
                                   'answered_from_saved', 'slot_hold_expired',
                                   'daily_note_drafted', 'daily_note_edited', 'daily_note_confirmed', 'daily_note_sent', 'agent_requeued'"""
PREVIOUS_KINDS = """'needs_info', 'new_card', 'urgent_complaint', 'uncertain_complaint',
                                  'director_report', 'on_hold', 'sent_or_booked', 'parent_confirmed',
                                  'completed', 'rejected', 'note_sent',
                                  'slot_hold_expired', 'hold_resumed'"""
NEW_ACTIONS = "'consultation_delay_reported', 'consultation_reminded'"
NEW_KINDS = "'consultation_ending', 'consultation_delayed'"


def upgrade():
    op.execute("""
        ALTER TABLE consultation_bookings ADD COLUMN expected_end_at timestamptz
            CONSTRAINT consultation_bookings_expected_end_check
            CHECK (isfinite(expected_end_at) AND expected_end_at > upper(period));
        ALTER TABLE events DROP CONSTRAINT events_action_check;
        ALTER TABLE notifications DROP CONSTRAINT notifications_kind_check;
    """)
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}, {NEW_ACTIONS}))")
    op.execute(f"ALTER TABLE notifications ADD CONSTRAINT notifications_kind_check CHECK (kind IN ({PREVIOUS_KINDS}, {NEW_KINDS}))")


def downgrade():
    # 이 기능의 새 알림·이력·지연 시각만 지워요. 예약·다른 이력과 알림은 남겨요.
    op.execute(f"DELETE FROM notifications WHERE kind IN ({NEW_KINDS})")
    op.execute(f"DELETE FROM events WHERE action IN ({NEW_ACTIONS})")
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute("ALTER TABLE notifications DROP CONSTRAINT notifications_kind_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}))")
    op.execute(f"ALTER TABLE notifications ADD CONSTRAINT notifications_kind_check CHECK (kind IN ({PREVIOUS_KINDS}))")
    op.drop_column("consultation_bookings", "expected_end_at")
