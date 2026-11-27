"""요청의 알림/부탁 분류(intent)를 저장해요. 감독 AI가 문의만 나누고, 투약·귀가는 조회할 때 늘 부탁으로 봐요."""

from alembic import op

revision = "0022"
down_revision = "0021"
branch_labels = None
depends_on = None


def upgrade():
    # 기존 요청은 NULL(분류 없음)로 둬요. 투약·귀가는 저장값과 관계없이 조회 때 'ask'라 백필하지 않아요.
    op.execute("ALTER TABLE requests ADD COLUMN intent text CHECK (intent IN ('notice', 'ask'))")


def downgrade():
    op.execute("ALTER TABLE requests DROP COLUMN intent")
