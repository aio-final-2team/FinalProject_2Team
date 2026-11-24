"""문의·상담에도 위험 등급이 저장되고, 위험한 문의는 자료 AI를 부르지 않고 사람에게 넘어가요."""

from uuid import uuid4

from alembic import command
from sqlalchemy import text

from app.core.db import transaction
from app.mock import seed
from tests.integration.db.test_answer_t33 import Writer, create_card, setup_graph


def test_risky_inquiry_skips_answer_model_and_saves_risk(db_client, seeded_db, monkeypatch):
    setup_graph(seeded_db, monkeypatch, {"text": "[TEST] 쓰면 안 되는 초안", "evidence": []})
    card, evidence, messages = create_card(db_client, "[TEST] 경찰에 알릴 거예요")
    assert Writer.calls == []  # 자료·검사 AI 모두 안 불렀어요
    assert not card["draft"].get("text") and card["check_result"] is None and evidence == [] and messages == 1
    with transaction() as connection:
        req = connection.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": card["request_id"]}).mappings().one()
        kinds = connection.scalars(text("SELECT kind FROM cards WHERE request_id=:id ORDER BY kind"),
                                   {"id": card["request_id"]}).all()
    assert (req["type"], req["status"], req["risk_level"], req["risk_category"]) == (
        "inquiry", "escalated", "urgent", "legal_external")
    assert kinds == ["director_report", "reply_draft"]


def test_0011_round_trip_keeps_complaint_risk_and_clears_other_types(seeded_db, alembic_config):
    rows = {kind: uuid4() for kind in ("inquiry", "consultation", "complaint")}
    with seeded_db.begin() as connection:
        for kind, request_id in rows.items():
            connection.execute(text("""
                INSERT INTO requests (id,org_id,classroom_id,child_id,requester_id,client_request_id,type,body,
                                      risk_level,risk_category)
                VALUES (:id,:org,:class,:child,:parent,:key,:type,'[TEST] 위험 등급','urgent','child_safety')
            """), {"id": request_id, "org": seed.ORG, "class": seed.CLASS_STAR, "child": seed.CHILD,
                   "parent": seed.PARENT, "key": f"test-0011-{kind}", "type": kind})
    command.downgrade(alembic_config, "0010")
    with seeded_db.connect() as connection:
        saved = dict(connection.execute(text("SELECT type,risk_level FROM requests WHERE id = ANY(:ids)"),
                                        {"ids": list(rows.values())}).all())
    assert saved == {"inquiry": None, "consultation": None, "complaint": "urgent"}
    command.upgrade(alembic_config, "head")
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE requests SET risk_level='uncertain' WHERE id=:id"), {"id": rows["inquiry"]})
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0012"
