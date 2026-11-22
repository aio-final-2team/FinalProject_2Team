"""[제안][선택] 가상 음성 결과만 저장하고 파일은 분석 뒤 지워요."""

from importlib import import_module
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None
_previous = import_module("apps.api.migrations.versions.0011_video_consult")
PREVIOUS_ACTIONS = f"{_previous.PREVIOUS_ACTIONS}, {_previous.NEW_ACTIONS}"
NEW_ACTIONS = "'voice_analysis_requested', 'voice_analysis_completed'"
DDL = """
CREATE TABLE consultation_voice_analyses (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           uuid NOT NULL,
    booking_id       uuid NOT NULL,
    request_id       uuid NOT NULL,
    storage_path     text,
    sha256           text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    duration_seconds double precision CHECK (duration_seconds >= 0 AND duration_seconds < 'Infinity'::float8),
    status           text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed')),
    transcript       text NOT NULL DEFAULT '',
    result           jsonb NOT NULL DEFAULT '{"summary":"","parent_requests":[],"follow_ups":[]}',
    created_at       timestamptz NOT NULL DEFAULT now(),
    started_at       timestamptz,
    completed_at     timestamptz,
    FOREIGN KEY (booking_id, org_id) REFERENCES consultation_bookings(id, org_id),
    FOREIGN KEY (request_id, org_id) REFERENCES requests(id, org_id)
);
CREATE INDEX consultation_voice_analyses_booking_idx ON consultation_voice_analyses (booking_id, created_at DESC, id DESC);
"""


def upgrade():
    op.execute("ALTER TABLE consultation_bookings ADD CONSTRAINT consultation_bookings_id_org_key UNIQUE (id, org_id)")
    op.execute(DDL)
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}, {NEW_ACTIONS}))")


def downgrade():
    op.execute("DROP TABLE consultation_voice_analyses")
    op.execute("ALTER TABLE consultation_bookings DROP CONSTRAINT consultation_bookings_id_org_key")
    op.execute(f"DELETE FROM events WHERE action IN ({NEW_ACTIONS})")
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}))")
