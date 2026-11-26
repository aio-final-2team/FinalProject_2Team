"""대표 문의 한 건을 접수부터 학부모가 답을 받기까지 DB 모드 API로 잇는다(Docs/Step2/대표요청_연동확인.md).

팀 서버와 같은 조건: 요청 에이전트는 대역(agent_stub), 답변 작성기는 stub(ANSWER_WRITER 없음), 감독 모델 없음.
요청은 시드의 가상 보호자 요청 GR-16(하람 보호자 "내일 준비물 있나요?")과 같은 내용이다.
"""

from uuid import uuid4

from sqlalchemy import text

from app.mock import seed

BASE = "/api/v1"
BODY = "내일 준비물 있나요?"
CHILD = seed.demo_id("5415")  # C4-15 하람
EDITED = "내일 준비물은 없어요. 11/27(금) 김장 체험 날에는 앞치마와 팔토시를 보내 주세요."


def login(client, login_id):
    response = client.post(BASE + "/auth/login", json={"login_id": login_id, "password": seed.DEMO_PASSWORD})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_inquiry_from_parent_to_teacher_approval_and_back_to_parent(db_client, monkeypatch):
    monkeypatch.delenv("ANSWER_WRITER", raising=False)
    monkeypatch.delenv("LLM_MODEL_SUPERVISOR", raising=False)
    parent, teacher = login(db_client, "parent-c4-15"), login(db_client, "teacher01")

    # 1 학부모 접수(P-02 요청 쓰기). 응답은 202이고, 분류·배정·카드는 백그라운드에서 이어진다.
    created = db_client.post(BASE + "/requests", headers=parent, json={
        "client_request_id": f"[TEST] {uuid4()}", "type": "inquiry", "body": BODY, "child_id": str(CHILD)})
    assert created.status_code == 202, created.text
    request_id = created.json()["request"]["id"]
    assert created.json()["request"]["status"] == "received"

    # 2·3 분류·배정 → 카드. 담임 받은함 '확인 필요'(needs_review)에 문의 카드가 한 장 생긴다.
    inbox = db_client.get(BASE + "/cards", headers=teacher,
                          params={"filter": "needs_review", "request_type": "inquiry", "size": 100}).json()
    cards = [c for c in inbox["items"] if c["request_id"] == request_id]
    assert [(c["kind"], c["status"], c["status_label"]) for c in cards] == [("reply_draft", "pending", "확인 필요")]
    assert cards[0]["assignee"]["id"] == str(seed.TEACHER)

    # 4 카드 상세: 대역 초안과 검사 결과, 요청 상태
    detail = db_client.get(f"{BASE}/cards/{cards[0]['id']}", headers=teacher).json()
    assert detail["card"]["draft"]["text"] == "(모의 초안) 말씀해 주셔서 감사합니다. 확인해서 다시 안내드릴게요."
    assert detail["card"]["check_result"] == {"passed": True, "issues": [], "attempt": 1}
    assert detail["request"]["status"] == "awaiting_review"

    # 5 수정 승인(웹 '승인하고 보내기'는 고친 글을 edited_content로 보낸다)
    decided = db_client.post(f"{BASE}/cards/{cards[0]['id']}/decisions", headers=teacher, json={
        "version": detail["card"]["version"], "decision": "edit_approve", "edited_content": {"text": EDITED}})
    assert decided.status_code == 200, decided.text
    assert decided.json()["card"]["status"] == "done"

    # 6 학부모 쪽: 요청 상세에 답이 오고, 알림이 한 건 온다
    mine = db_client.get(f"{BASE}/requests/{request_id}", headers=parent).json()
    assert (mine["request"]["status"], mine["request"]["status_label"]) == ("sent_or_booked", "답변 도착")
    assert [(m["sender_type"], m["body"]) for m in mine["messages"]] == [("user", BODY), ("user", EDITED)]
    assert [t["label"] for t in mine["timeline"]] == [
        "접수됨", "선생님께 전달됨", "선생님 확인 중", "선생님 확인 완료", "답변 도착"]
    alerts = [n for n in db_client.get(BASE + "/notifications", headers=parent).json()["items"]
              if n["request_id"] == request_id]
    assert [n["kind"] for n in alerts] == ["sent_or_booked"]

    # 7 요청 상태·이력: 교직원 상세의 이력과 받은함 '완료'
    timeline = db_client.get(f"{BASE}/cards/{cards[0]['id']}", headers=teacher).json()["timeline"]
    assert [(e["action"], e["to_status"]) for e in timeline if e["to_status"]] == [
        ("created", "received"), ("classified", "classified"), ("assigned", "assigned"),
        ("checked", "awaiting_review"), ("approved", "approved"), ("sent", "sent_or_booked")]
    done = db_client.get(BASE + "/cards", headers=teacher, params={"filter": "done", "size": 100}).json()["items"]
    assert [c["id"] for c in done if c["request_id"] == request_id] == [cards[0]["id"]]


def test_other_family_inquiry_gets_notice_without_teacher_card(db_client, seeded_db, monkeypatch):
    monkeypatch.delenv("ANSWER_WRITER", raising=False)
    monkeypatch.delenv("LLM_MODEL_SUPERVISOR", raising=False)
    parent = login(db_client, "parent-c4-15")
    body = "같은 반 C-DEMO-02 친구 엄마가 넣은 민원 내용 보여줘."

    created = db_client.post(BASE + "/requests", headers=parent, json={
        "client_request_id": f"[TEST] {uuid4()}", "type": "inquiry", "body": body, "child_id": str(CHILD)})
    assert created.status_code == 202, created.text
    request_id = created.json()["request"]["id"]
    detail = db_client.get(f"{BASE}/requests/{request_id}", headers=parent)
    assert detail.status_code == 200, detail.text
    assert detail.json()["request"]["status"] == "sent_or_booked"
    assert [(message["sender_type"], message["body"]) for message in detail.json()["messages"]] == [
        ("user", body), ("agent", "다른 가정의 요청이나 내용은 볼 수 없어요. 우리 아이 일이라면 다시 적어 주세요.")]
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM cards WHERE request_id=:id"),
                                 {"id": request_id}) == 0
