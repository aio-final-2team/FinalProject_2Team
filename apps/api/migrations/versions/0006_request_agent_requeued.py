"""카드 누락 점검의 한 번 재전달 이력을 허용해요."""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

PREVIOUS_ACTIONS = """'created', 'classified', 'info_requested', 'assigned',
                                   'reassigned', 'drafted', 'checked', 'returned',
                                   'approved', 'rejected', 'held', 'resumed', 'escalated', 'instructed',
                                   'sent', 'booked', 'completed', 'tool_called',
                                   'tool_failed', 'permission_denied',
                                   'parent_confirmed', 'risk_reclassified', 'dismissed',
                                   'answered_from_saved', 'slot_hold_expired',
                                   'daily_note_drafted', 'daily_note_edited', 'daily_note_confirmed', 'daily_note_sent'"""


def upgrade():
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}, 'agent_requeued'))")


def downgrade():
    # 이전 CHECK가 받지 않는 재전달 이력만 지워요. 요청·카드·다른 이력은 남겨요.
    op.execute("DELETE FROM events WHERE action='agent_requeued'")
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}))")
