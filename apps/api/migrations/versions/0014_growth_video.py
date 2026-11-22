"""[제안][선택] 성장 영상 메타데이터와 사진 순서예요."""

from importlib import import_module
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None
_previous = import_module("apps.api.migrations.versions.0012_voice_analysis")
PREVIOUS_ACTIONS = f"{_previous.PREVIOUS_ACTIONS}, {_previous.NEW_ACTIONS}"
NEW_ACTIONS = "'growth_video_requested', 'growth_video_completed', 'growth_video_deleted'"
DDL = """
CREATE TABLE growth_videos (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id uuid NOT NULL,
    child_id uuid NOT NULL,
    requested_by uuid NOT NULL,
    status text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued','running','succeeded','failed')),
    storage_path text NOT NULL,
    photo_count integer NOT NULL CHECK (photo_count BETWEEN 3 AND 20),
    duration_seconds double precision CHECK (duration_seconds > 0 AND duration_seconds <= 60),
    size_bytes bigint CHECK (size_bytes > 0),
    sha256 text CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    created_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    completed_at timestamptz,
    deleted_at timestamptz,
    UNIQUE (id, org_id),
    FOREIGN KEY (child_id, org_id) REFERENCES children(id, org_id),
    FOREIGN KEY (requested_by, org_id) REFERENCES users(id, org_id)
);
CREATE INDEX growth_videos_child_idx ON growth_videos (child_id, created_at DESC, id DESC);
CREATE TABLE growth_video_photos (
    video_id uuid NOT NULL,
    org_id uuid NOT NULL,
    photo_id uuid NOT NULL,
    position integer NOT NULL CHECK (position BETWEEN 0 AND 19),
    PRIMARY KEY (video_id, position),
    UNIQUE (video_id, photo_id),
    FOREIGN KEY (video_id, org_id) REFERENCES growth_videos(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (photo_id, org_id) REFERENCES feed_photos(id, org_id) ON DELETE CASCADE
);
"""


def upgrade():
    op.execute(DDL)
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}, {NEW_ACTIONS}))")


def downgrade():
    op.execute("DROP TABLE growth_video_photos; DROP TABLE growth_videos")
    op.execute(f"DELETE FROM events WHERE action IN ({NEW_ACTIONS})")
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}))")
