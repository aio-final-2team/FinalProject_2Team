"""T19: v0.7 DDL 적용본. 본문은 설계 초안과 같다."""

from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    sql = Path(__file__).resolve().parents[1] / "sql" / "0001_initial.sql"
    op.execute(sql.read_text(encoding="utf-8"))


def downgrade():
    op.execute("DROP VIEW director_overview, staff_inbox")
    # 자식부터 지운다. 표에 붙은 인덱스·제약·트리거도 함께 사라진다.
    for table in (
        "eval_runs", "notifications", "daily_notes", "daily_note_inputs",
        "saved_answer_sources", "saved_answers", "memory_rules", "memories",
        "consultation_bookings", "consultation_slots", "staff_busy_blocks", "rooms",
        "events", "approvals", "card_evidence", "cards", "document_classrooms",
        "document_chunks", "documents", "request_messages", "requests",
        "child_guardians", "children", "classroom_staff", "users", "classrooms", "organizations",
    ):
        op.drop_table(table)
    op.execute("DROP FUNCTION invalidate_saved_answers(), require_reason_for_unconfirmed_complete()")
    op.execute("DROP EXTENSION btree_gist")
    op.execute("DROP EXTENSION vector")
