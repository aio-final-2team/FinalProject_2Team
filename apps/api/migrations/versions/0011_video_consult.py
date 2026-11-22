"""[제안][선택] T56 접속·퇴장 이력을 더해요. 영상·신호 저장 표는 없어요."""

from importlib import import_module

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_previous = import_module("apps.api.migrations.versions.0010_feed_albums")
PREVIOUS_ACTIONS = f"{_previous.PREVIOUS_ACTIONS}, {_previous.NEW_ACTIONS}"
NEW_ACTIONS = "'video_joined', 'video_left'"


def upgrade():
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}, {NEW_ACTIONS}))")


def downgrade():
    op.execute(f"DELETE FROM events WHERE action IN ({NEW_ACTIONS})")
    op.execute("ALTER TABLE events DROP CONSTRAINT events_action_check")
    op.execute(f"ALTER TABLE events ADD CONSTRAINT events_action_check CHECK (action IN ({PREVIOUS_ACTIONS}))")
