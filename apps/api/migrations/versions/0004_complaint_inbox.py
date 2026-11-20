"""발송한 민원 회신을 처리 완료 전까지 받은함에 남겨요(v0.10)."""

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
CREATE OR REPLACE VIEW staff_inbox AS
SELECT
    c.id            AS card_id,
    c.org_id,
    c.assignee_id,
    c.kind,
    c.status        AS card_status,
    c.version,
    c.due_at,
    c.hold_until,
    c.closed_at,
    r.id            AS request_id,
    r.classroom_id,
    r.type          AS request_type,
    r.status        AS request_status,
    r.risk_level,
    r.parent_confirmed_at,
    (r.risk_level = 'urgent') IS TRUE AS is_urgent,
    CASE
        WHEN (c.status IN ('rejected', 'done') AND NOT (
                r.type = 'complaint' AND r.status = 'sent_or_booked'
                AND c.kind = 'reply_draft' AND c.status <> 'rejected') IS TRUE)
          OR r.status IN ('completed', 'rejected')
            THEN 'done'
        WHEN c.status = 'on_hold' OR r.status = 'on_hold'
            THEN 'on_hold'
        WHEN c.assignee_id IS NULL
            THEN 'unassigned'
        WHEN r.risk_level = 'uncertain'
            THEN 'uncertain'
        WHEN r.status IN ('awaiting_review', 'escalated')
          OR (r.type = 'complaint' AND r.status = 'sent_or_booked' AND r.parent_confirmed_at IS NOT NULL)
          OR (c.request_id IS NULL AND c.status IN ('pending', 'in_review'))
            THEN 'needs_review'
        ELSE 'in_progress'
    END AS inbox_filter
FROM cards c
LEFT JOIN requests r ON r.id = c.request_id;
    """)


def downgrade():
    op.execute("""
CREATE OR REPLACE VIEW staff_inbox AS
SELECT
    c.id            AS card_id,
    c.org_id,
    c.assignee_id,
    c.kind,
    c.status        AS card_status,
    c.version,
    c.due_at,
    c.hold_until,
    c.closed_at,
    r.id            AS request_id,
    r.classroom_id,
    r.type          AS request_type,
    r.status        AS request_status,
    r.risk_level,
    r.parent_confirmed_at,
    (r.risk_level = 'urgent') IS TRUE AS is_urgent,
    CASE
        WHEN c.status IN ('rejected', 'done') OR r.status IN ('completed', 'rejected')
            THEN 'done'
        WHEN c.status = 'on_hold' OR r.status = 'on_hold'
            THEN 'on_hold'
        WHEN c.assignee_id IS NULL
            THEN 'unassigned'
        WHEN r.risk_level = 'uncertain'
            THEN 'uncertain'
        WHEN r.status IN ('awaiting_review', 'escalated')
          OR (r.type = 'complaint' AND r.status = 'sent_or_booked' AND r.parent_confirmed_at IS NOT NULL)
          OR (c.request_id IS NULL AND c.status IN ('pending', 'in_review'))
            THEN 'needs_review'
        ELSE 'in_progress'
    END AS inbox_filter
FROM cards c
LEFT JOIN requests r ON r.id = c.request_id;
    """)
