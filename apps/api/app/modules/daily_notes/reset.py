"""QA 알림장 초기화. 입력 잠금부터 감사 기록까지 한 트랜잭션이에요."""

import json

from sqlalchemy import text

from app.core.db import transaction
from app.core.scope import classroom_in_scope


def reset(user, classroom_id, note_date):
    with transaction() as connection:
        classroom_in_scope(user, classroom_id, connection=connection)
        values = {"org": user.org_id, "class": classroom_id, "date": note_date}
        inputs = connection.scalars(text("""
            SELECT id FROM daily_note_inputs
            WHERE org_id=:org AND classroom_id=:class AND note_date=:date FOR UPDATE
        """), values).all()
        values["inputs"] = inputs
        values["notes"] = connection.scalars(text("""
            SELECT id FROM daily_notes WHERE org_id=:org AND input_id=ANY(CAST(:inputs AS uuid[]))
        """), values).all()
        values["cards"] = connection.scalars(text("""
            SELECT id FROM cards WHERE org_id=:org AND subject_type='daily_note_batch'
            AND subject_id=ANY(CAST(:inputs AS uuid[]))
        """), values).all()
        unlinked = connection.execute(text("""
            UPDATE requests SET source_note_id=NULL
            WHERE org_id=:org AND source_note_id=ANY(CAST(:notes AS uuid[]))
        """), values).rowcount
        deleted = {"inputs": len(inputs), "notes": len(values["notes"]), "cards": len(values["cards"])}
        for table, condition in (
            ("notifications", "card_id=ANY(CAST(:cards AS uuid[])) OR "
             "(subject_type='daily_note' AND subject_id=ANY(CAST(:notes AS uuid[])))"),
            ("events", "card_id=ANY(CAST(:cards AS uuid[])) OR daily_note_id=ANY(CAST(:notes AS uuid[]))"),
            ("approvals", "card_id=ANY(CAST(:cards AS uuid[]))"),
        ):
            count = connection.execute(text(f"DELETE FROM {table} WHERE org_id=:org AND ({condition})"), values).rowcount
            if table in ("notifications", "events"):
                deleted[table] = count
        for table in ("memories", "saved_answers"):
            # shortcut: 0001의 saved_answers 참조는 NOT NULL. 실제 참조가 있으면 전체 롤백;
            # nullable로 바꾸는 별도 스키마 작업 때 해소해요(알림장 카드는 승인 답 저장 대상이 아님).
            connection.execute(text(f"UPDATE {table} SET source_card_id=NULL "
                                    "WHERE org_id=:org AND source_card_id=ANY(CAST(:cards AS uuid[]))"), values)
        for table, ids in (("cards", "cards"), ("daily_notes", "notes"), ("daily_note_inputs", "inputs")):
            connection.execute(text(f"DELETE FROM {table} WHERE org_id=:org AND id=ANY(CAST(:{ids} AS uuid[]))"), values)
        detail = {"tool": "qa_daily_note_reset", "classroom_id": str(classroom_id),
                  "note_date": note_date.isoformat(), "deleted": deleted}
        connection.execute(text("""
            INSERT INTO events(org_id,actor_type,actor_id,action,detail)
            VALUES (:org,'user',:actor,'tool_called',CAST(:detail AS jsonb))
        """), {"org": user.org_id, "actor": user.id, "detail": json.dumps(detail)})
    return {"classroom_id": classroom_id, "note_date": note_date,
            "deleted": deleted, "unlinked_replies": unlinked}
