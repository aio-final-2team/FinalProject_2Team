"""아이 프로필 사진 경로와 원별 급식 참고 사진을 저장해요. 파일은 MEDIA_DIR 하위 폴더에 둬요."""

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade():
    # profiles/<child_id>.<확장자>. 고아 파일 점검(media_sweep)이 이 열과 대조해요. meals/는 점검 대상이 아니에요.
    op.execute("ALTER TABLE children ADD COLUMN profile_photo_path text")
    op.execute("""
        CREATE TABLE meal_photos (
            org_id uuid NOT NULL REFERENCES organizations(id),
            meal_date date NOT NULL,
            main_dish text NOT NULL,
            storage_path text NOT NULL,
            media_type text NOT NULL CHECK (media_type IN ('image/jpeg', 'image/png', 'image/webp')),
            size_bytes integer NOT NULL CHECK (size_bytes > 0),
            created_at timestamptz NOT NULL DEFAULT now(),
            PRIMARY KEY (org_id, meal_date)
        )
    """)


def downgrade():
    op.drop_table("meal_photos")
    op.execute("ALTER TABLE children DROP COLUMN profile_photo_path")
