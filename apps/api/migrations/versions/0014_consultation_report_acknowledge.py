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
    # 새 결정 행은 보존하고, 이후 쓰기에만 이전 계약을 적용해요(0012와 같은 관례).
    op.execute("ALTER TABLE approvals DROP CONSTRAINT approvals_decision_check")
    op.execute(f"ALTER TABLE approvals ADD CONSTRAINT approvals_decision_check CHECK (decision IN ({PREVIOUS})) NOT VALID")
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM approvals WHERE decision='acknowledge') THEN
                ALTER TABLE approvals VALIDATE CONSTRAINT approvals_decision_check;
            END IF;
        END $$
    """)
