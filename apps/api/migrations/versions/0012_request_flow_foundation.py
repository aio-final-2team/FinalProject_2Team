"""요청 흐름 이력·알림을 넓히고 투약·귀가 입력을 요청에 모아요."""

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

# 마이그레이션은 이후 애플리케이션 상수가 바뀌어도 같은 스키마를 만들어야 해요.
PREVIOUS_ACTIONS = """'created', 'classified', 'info_requested', 'assigned',
    'reassigned', 'drafted', 'checked', 'returned', 'approved', 'rejected', 'held', 'resumed',
    'escalated', 'instructed', 'sent', 'booked', 'completed', 'tool_called', 'tool_failed',
    'permission_denied', 'parent_confirmed', 'risk_reclassified', 'dismissed',
    'answered_from_saved', 'slot_hold_expired', 'daily_note_drafted', 'daily_note_edited',
    'daily_note_confirmed', 'daily_note_sent', 'agent_requeued', 'consultation_delay_reported',
    'consultation_reminded', 'feed_post_created', 'feed_post_deleted', 'feed_post_hidden', 'photo_scope_changed'"""
NEW_ACTIONS = """'message_added', 'out_of_scope_answered', 'cancelled', 'care_updated',
    'daily_note_corrected', 'slot_conflict_reproposed', 'report_acknowledged'"""
PREVIOUS_KINDS = """'needs_info', 'new_card', 'urgent_complaint', 'uncertain_complaint',
    'director_report', 'on_hold', 'sent_or_booked', 'parent_confirmed', 'completed', 'rejected',
    'note_sent', 'slot_hold_expired', 'hold_resumed', 'consultation_ending', 'consultation_delayed',
    'care_requested', 'care_confirmed'"""
NEW_KINDS = """'parent_message', 'reassigned', 'consultation_booked', 'note_corrected',
    'cancelled', 'care_rejected'"""
CARE_FIELDS = """'pickup_guardian_id', 'pickup_name', 'pickup_relation',
    'medication_name', 'medication_dose', 'medication_time'"""
RECEIPTS = """
    SELECT DISTINCT ON (e.request_id) e.id, e.request_id, e.detail
    FROM events e JOIN requests r ON (r.id,r.org_id)=(e.request_id,e.org_id)
    WHERE r.type IN ('medication','pickup') AND e.action='created'
      AND e.to_status='received' AND e.card_id IS NULL
    ORDER BY e.request_id,e.id
"""


def _replace_check(table, column, values, *, preserve_existing=False):
    constraint = f"{table}_{column}_check"
    op.execute(f"ALTER TABLE {table} DROP CONSTRAINT {constraint}")
    suffix = " NOT VALID" if preserve_existing else ""
    op.execute(f"ALTER TABLE {table} ADD CONSTRAINT {constraint} CHECK ({column} IN ({values})){suffix}")
    if preserve_existing:
        # 새 값의 기존 행은 보존하고, 이후 쓰기에는 이전 값 목록을 적용해요.
        # 새 값이 없으면 검증까지 마쳐 0011의 원래 스키마와 같게 돌려요.
        op.execute(f"""
            DO $$ BEGIN
                IF NOT EXISTS (SELECT 1 FROM {table} WHERE {column} NOT IN ({values})) THEN
                    ALTER TABLE {table} VALIDATE CONSTRAINT {constraint};
                END IF;
            END $$
        """)


def upgrade():
    op.execute("ALTER TABLE requests ADD COLUMN care_detail jsonb NOT NULL DEFAULT '{}'")
    _replace_check("events", "action", f"{PREVIOUS_ACTIONS}, {NEW_ACTIONS}")
    _replace_check("notifications", "kind", f"{PREVIOUS_KINDS}, {NEW_KINDS}")
    op.execute(f"""
        WITH receipts AS ({RECEIPTS})
        UPDATE requests r SET care_detail=COALESCE(
            (SELECT jsonb_object_agg(key,value) FROM jsonb_each(e.detail)
             WHERE key=ANY(ARRAY[{CARE_FIELDS}])), '{{}}'::jsonb)
        FROM receipts e WHERE r.id=e.request_id;

        UPDATE events e SET detail=(e.detail - ARRAY[{CARE_FIELDS}]) || jsonb_build_object(
            'fields', COALESCE((SELECT jsonb_agg(key ORDER BY key) FROM jsonb_object_keys(e.detail) AS key
                               WHERE key=ANY(ARRAY[{CARE_FIELDS}])), '[]'::jsonb))
        FROM requests r WHERE (r.id,r.org_id)=(e.request_id,e.org_id)
          AND r.type IN ('medication','pickup') AND e.action='created'
          AND e.to_status='received' AND e.card_id IS NULL
    """)


def downgrade():
    # 이력 ID·행위자·시각·추적 정보는 그대로 두고 접수 입력만 되돌려요.
    op.execute(f"""
        WITH receipts AS ({RECEIPTS})
        UPDATE events e SET detail=(e.detail - 'fields') || r.care_detail
        FROM receipts receipt JOIN requests r ON r.id=receipt.request_id
        WHERE e.id=receipt.id
    """)
    op.drop_column("requests", "care_detail")
    _replace_check("events", "action", PREVIOUS_ACTIONS, preserve_existing=True)
    _replace_check("notifications", "kind", PREVIOUS_KINDS, preserve_existing=True)
