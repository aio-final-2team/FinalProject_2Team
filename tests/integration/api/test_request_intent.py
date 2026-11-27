"""요청 의도(알림/부탁)를 교직원 요청·카드 조회에 내보내요. 모의 백엔드엔 AI가 없어 #408 대역 값(ask)이에요."""

from uuid import UUID, uuid4

from app.mock import seed, store
from tests.integration.api.helpers import BASE


def test_mock_inquiry_gets_fallback_ask_on_staff_views_only(client, parent, teacher):
    body = "[TEST] 금요일엔 외삼촌이 데리러 갈 예정입니다"
    created = client.post(BASE + "/requests", headers=parent, json={
        "client_request_id": str(uuid4()), "type": "inquiry", "child_id": str(seed.CHILD), "body": body})
    assert created.status_code == 202, created.text
    rid = created.json()["request"]["id"]
    assert store.state().requests[UUID(rid)].intent == "ask"
    staff = client.get(BASE + "/requests?size=100", headers=teacher).json()["items"]
    assert next(r for r in staff if r["id"] == rid)["intent"] == "ask"
    card = next(c for c in store.cards_of(UUID(rid)) if c.kind == "reply_draft")
    listed = client.get(BASE + "/cards?filter=needs_review&request_type=inquiry&size=100", headers=teacher).json()["items"]
    assert next(c for c in listed if c["id"] == str(card.id))["intent"] == "ask"
    assert client.get(f"{BASE}/cards/{card.id}", headers=teacher).json()["request"]["intent"] == "ask"
    # 분류가 없는 요청(접수만 된 시드 문의)은 값이 없고, 학부모 화면 계약에는 의도를 싣지 않아요.
    assert next(r for r in staff if r["id"] == str(seed.REQUEST_COUGH))["intent"] is None
    assert "intent" not in client.get(f"{BASE}/requests/{rid}", headers=parent).json()["request"]
