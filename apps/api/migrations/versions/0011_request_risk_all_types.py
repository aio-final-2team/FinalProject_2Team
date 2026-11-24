"""위험 등급을 민원뿐 아니라 문의·상담에도 저장할 수 있게 해요(기획서 FR-03)."""

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade():
    # 0001에서 이름 없이 만든 표 CHECK라 PostgreSQL이 붙인 이름(requests_check1)을 그대로 이어 써요.
    op.execute("""
        ALTER TABLE requests DROP CONSTRAINT requests_check1,
            ADD CONSTRAINT requests_check1
            CHECK (risk_level IS NULL OR type IN ('inquiry', 'consultation', 'complaint'))
    """)


def downgrade():
    # 예전 규칙은 민원만 위험 등급을 가져요. 문의·상담에 붙은 등급은 지우고 되돌려요.
    op.execute("UPDATE requests SET risk_level=NULL, risk_category=NULL WHERE type <> 'complaint'")
    op.execute("""
        ALTER TABLE requests DROP CONSTRAINT requests_check1,
            ADD CONSTRAINT requests_check1 CHECK (risk_level IS NULL OR type = 'complaint')
    """)
