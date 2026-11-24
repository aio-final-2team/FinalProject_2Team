"""상담 원장 보고 확인을 사람의 결정 이력에 남겨요."""

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

PREVIOUS = "'approve','edit_approve','reject','hold','resume','dismiss','complete','escalate','instruct'"


def upgrade():
    op.execute("ALTER TABLE approvals DROP CONSTRAINT approvals_decision_check")
    op.execute(f"ALTER TABLE approvals ADD CONSTRAINT approvals_decision_check CHECK (decision IN ({PREVIOUS},'acknowledge'))")


def downgrade():
    # 이전 코드가 읽지 못하는 새 결정은 지우고 원래 제약으로 돌려요.
    op.execute("DELETE FROM approvals WHERE decision='acknowledge'")
    op.execute("ALTER TABLE approvals DROP CONSTRAINT approvals_decision_check")
    op.execute(f"ALTER TABLE approvals ADD CONSTRAINT approvals_decision_check CHECK (decision IN ({PREVIOUS}))")
