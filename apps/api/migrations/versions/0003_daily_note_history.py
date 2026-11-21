"""알림장 최초 초안과 아이별 상태 이력을 보관한다(v0.9)."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NOTE_ACTIONS = "'daily_note_drafted', 'daily_note_edited', 'daily_note_confirmed', 'daily_note_sent'"


ORIGINAL_ACTIONS = """'created', 'classified', 'info_requested', 'assigned',
                                   'reassigned', 'drafted', 'checked', 'returned',
                                   'approved', 'rejected', 'held', 'resumed', 'escalated', 'instructed',
                                   'sent', 'booked', 'completed', 'tool_called',
                                   'tool_failed', 'permission_denied',
                                   'parent_confirmed', 'risk_reclassified', 'dismissed',
                                   'answered_from_saved', 'slot_hold_expired'"""


def upgrade():
    op.execute("""
        ALTER TABLE daily_notes ADD COLUMN ai_original jsonb NOT NULL DEFAULT '{}'::jsonb;
        UPDATE daily_notes SET ai_original=content;
        ALTER TABLE daily_notes ADD CONSTRAINT daily_notes_id_org_key UNIQUE (id, org_id);
        ALTER TABLE events ADD COLUMN daily_note_id uuid;
        ALTER TABLE events ADD CONSTRAINT events_daily_note_org_fkey
            FOREIGN KEY (daily_note_id, org_id) REFERENCES daily_notes(id, org_id);
        CREATE INDEX events_daily_note_idx ON events (daily_note_id, id);
        ALTER TABLE events DROP CONSTRAINT events_action_check;
    """)
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({ORIGINAL_ACTIONS}, {NOTE_ACTIONS}))")


def downgrade():
    # 새 종류 이력은 옛 CHECK가 받지 않으므로 이 마이그레이션의 이력만 없앤다.
    op.execute(f"DELETE FROM events WHERE action IN ({NOTE_ACTIONS})")
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({ORIGINAL_ACTIONS}))")
    op.drop_index("events_daily_note_idx", table_name="events")
    op.drop_column("events", "daily_note_id")
    op.drop_constraint("daily_notes_id_org_key", "daily_notes", type_="unique")
    op.drop_column("daily_notes", "ai_original")
