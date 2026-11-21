"""[제안] T54 피드·사진 메타데이터와 아이별 공개 범위를 더해요."""

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

PREVIOUS_ACTIONS = """'created', 'classified', 'info_requested', 'assigned',
                                   'reassigned', 'drafted', 'checked', 'returned',
                                   'approved', 'rejected', 'held', 'resumed', 'escalated', 'instructed',
                                   'sent', 'booked', 'completed', 'tool_called',
                                   'tool_failed', 'permission_denied',
                                   'parent_confirmed', 'risk_reclassified', 'dismissed',
                                   'answered_from_saved', 'slot_hold_expired',
                                   'daily_note_drafted', 'daily_note_edited', 'daily_note_confirmed', 'daily_note_sent', 'agent_requeued',
                                   'consultation_delay_reported', 'consultation_reminded'"""
NEW_ACTIONS = "'feed_post_created', 'feed_post_deleted', 'feed_post_hidden', 'photo_scope_changed'"


def upgrade():
    op.execute("""
        ALTER TABLE children ADD COLUMN photo_scope text NOT NULL DEFAULT 'family'
            CONSTRAINT children_photo_scope_check CHECK (photo_scope IN ('family', 'class', 'org'));
CREATE TABLE feed_posts (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES organizations(id),
    classroom_id  uuid,
    lane          text NOT NULL CHECK (lane IN ('class', 'org')),
    author_id     uuid NOT NULL,
    body          text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000 AND btrim(body) <> ''),
    status        text NOT NULL DEFAULT 'published' CHECK (status IN ('published', 'hidden')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz,
    CHECK ((lane='class' AND classroom_id IS NOT NULL) OR (lane='org' AND classroom_id IS NULL)),
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id),
    FOREIGN KEY (author_id, org_id) REFERENCES users(id, org_id),
    UNIQUE (id, org_id)
);
CREATE INDEX feed_posts_lane_time_idx ON feed_posts (org_id, lane, classroom_id, created_at DESC, id DESC)
    WHERE deleted_at IS NULL AND status='published';
CREATE TABLE feed_photos (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL,
    post_id       uuid NOT NULL,
    storage_path  text NOT NULL UNIQUE,
    media_type    text NOT NULL CHECK (media_type IN ('image/jpeg', 'image/png', 'image/webp')),
    size_bytes    integer NOT NULL CHECK (size_bytes BETWEEN 1 AND 5242880),
    sha256        text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    created_at    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (post_id, org_id) REFERENCES feed_posts(id, org_id),
    UNIQUE (id, org_id)
);
CREATE INDEX feed_photos_post_idx ON feed_photos (post_id, created_at, id);
CREATE TABLE feed_photo_children (
    org_id    uuid NOT NULL,
    photo_id  uuid NOT NULL,
    child_id  uuid NOT NULL,
    PRIMARY KEY (photo_id, child_id),
    FOREIGN KEY (photo_id, org_id) REFERENCES feed_photos(id, org_id),
    FOREIGN KEY (child_id, org_id) REFERENCES children(id, org_id)
);
CREATE INDEX feed_photo_children_child_idx ON feed_photo_children (child_id, photo_id);
    """)
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}, {NEW_ACTIONS}))")


def downgrade():
    # 파일 삭제는 앱에서 해요. downgrade는 파일 볼륨을 지우지 않아요.
    op.execute(f"DELETE FROM events WHERE action IN ({NEW_ACTIONS})")
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}))")
    op.drop_table("feed_photo_children")
    op.drop_table("feed_photos")
    op.drop_table("feed_posts")
    op.drop_column("children", "photo_scope")
