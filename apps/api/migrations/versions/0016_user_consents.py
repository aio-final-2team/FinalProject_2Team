"""[제안] 필수 동의 기록과 동의 이력 동작을 더해요. 동의 행은 시드에서 넣어요."""

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

PREVIOUS_ACTIONS = """'created', 'classified', 'info_requested', 'assigned',
    'reassigned', 'drafted', 'checked', 'returned', 'approved', 'rejected', 'held', 'resumed',
    'escalated', 'instructed', 'sent', 'booked', 'completed', 'tool_called', 'tool_failed',
    'permission_denied', 'parent_confirmed', 'risk_reclassified', 'dismissed',
    'answered_from_saved', 'slot_hold_expired', 'daily_note_drafted', 'daily_note_edited',
    'daily_note_confirmed', 'daily_note_sent', 'agent_requeued', 'consultation_delay_reported',
    'consultation_reminded', 'feed_post_created', 'feed_post_deleted', 'feed_post_hidden', 'photo_scope_changed',
    'message_added', 'out_of_scope_answered', 'cancelled', 'care_updated',
    'daily_note_corrected', 'slot_conflict_reproposed', 'report_acknowledged'"""


def upgrade():
    op.execute("""
        CREATE TABLE user_consents (
            id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
            org_id uuid NOT NULL REFERENCES organizations(id),
            user_id uuid NOT NULL,
            item text NOT NULL CHECK (item IN ('terms','privacy','ai_processing','child_info','child_health','child_face')),
            terms_version text NOT NULL,
            agreed_at timestamptz NOT NULL DEFAULT now(),
            FOREIGN KEY (user_id,org_id) REFERENCES users(id,org_id),
            UNIQUE (org_id,user_id,item,terms_version)
        )
    """)
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS},'consent_agreed'))")


def downgrade():
    op.drop_table("user_consents")
    # 이미 남긴 동의 이력은 되돌리기 때도 지우지 않아요(0012와 같은 보존 방식).
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS})) NOT VALID")
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM events WHERE action='consent_agreed') THEN
                ALTER TABLE events VALIDATE CONSTRAINT events_action_check;
            END IF;
        END $$
    """)
