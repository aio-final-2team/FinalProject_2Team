"""[제안][선택] 동네 칸과 사진 공개 범위를 더해요. 가상 기관은 데모 시드에서 넣어요."""

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def checks(lanes, scopes):
    other_lanes = "lane='org'" if lanes == "'class', 'org'" else "lane IN ('org', 'neighborhood')"
    op.execute("ALTER TABLE feed_posts DROP CONSTRAINT feed_posts_lane_check, DROP CONSTRAINT feed_posts_check")
    op.execute(f"ALTER TABLE feed_posts ADD CONSTRAINT feed_posts_lane_check CHECK (lane IN ({lanes}))")
    op.execute(f"""ALTER TABLE feed_posts ADD CONSTRAINT feed_posts_check CHECK (
        (lane='class' AND classroom_id IS NOT NULL) OR ({other_lanes} AND classroom_id IS NULL))""")
    op.execute("ALTER TABLE children DROP CONSTRAINT children_photo_scope_check")
    op.execute(f"ALTER TABLE children ADD CONSTRAINT children_photo_scope_check CHECK (photo_scope IN ({scopes}))")


def upgrade():
    checks("'class', 'org', 'neighborhood'", "'family', 'class', 'org', 'neighborhood'")


def downgrade():
    # 동네 글을 원 칸으로 옮기지 않아요. 새 칸만 지우고 기존 글·기관·계정은 보존해요.
    op.execute("""
        DELETE FROM feed_photo_children WHERE photo_id IN (
            SELECT id FROM feed_photos WHERE post_id IN (SELECT id FROM feed_posts WHERE lane='neighborhood'));
        DELETE FROM feed_photos WHERE post_id IN (SELECT id FROM feed_posts WHERE lane='neighborhood');
        DELETE FROM feed_posts WHERE lane='neighborhood';
        UPDATE children SET photo_scope='org' WHERE photo_scope='neighborhood';
    """)
    checks("'class', 'org'", "'family', 'class', 'org'")
