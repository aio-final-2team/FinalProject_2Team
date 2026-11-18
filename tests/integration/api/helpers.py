"""통합 시험에서 쓰는 요청 도우미."""

from uuid import UUID, uuid4
from app.mock import seed, store

BASE = "/api/v1"


def create(client, parent, type="complaint", body="버스가 늦었어요"):
    res = client.post(BASE + "/requests", headers=parent, json={"client_request_id": str(uuid4()),
                      "type": type, "body": body, "child_id": str(seed.CHILD)})
    assert res.status_code == 202, res.text
    rid = res.json()["request"]["id"]
    card = next(c for c in store.cards_of(UUID(rid)) if c.kind != "director_report")
    return rid, str(card.id)


def decision(client, teacher, card_id, decision="approve", version=1, **extra):
    return client.post(f"{BASE}/cards/{card_id}/decisions", headers=teacher,
                       json={"version": version, "decision": decision, **extra})


def err(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"] == code
    assert response.headers["X-Request-ID"] == response.json()["error"]["trace_id"]

