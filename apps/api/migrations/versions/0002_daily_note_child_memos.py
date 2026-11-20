"""알림장 입력에 아이별 메모 배열을 저장한다(v0.8)."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        ALTER TABLE daily_note_inputs
        ADD COLUMN child_memos jsonb NOT NULL DEFAULT '[]'::jsonb
            CONSTRAINT daily_note_inputs_child_memos_array
            CHECK (jsonb_typeof(child_memos) = 'array')
    """)


def downgrade():
    # 컬럼에 붙은 배열 CHECK도 함께 지운다. 저장한 아이별 메모는 사라진다.
    op.drop_column("daily_note_inputs", "child_memos")
