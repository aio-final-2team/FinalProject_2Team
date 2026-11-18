"""알림장·자료의 일괄 처리와 공개 범위."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import UUID, uuid4

import jwt
import pytest

from app.core.config import settings
from app.core.auth import issue_token
from app.mock import seed, store
from app.mock.records import Evidence
from tests.integration.api.helpers import BASE, create, decision, err


def draft(client, teacher, activities="블록 놀이와 산책", **extra):
    data = {"classroom_id": str(seed.CLASS_STAR), "note_date": store.now().date().isoformat(),
            "activities": activities, "supplies": "내일 실내화", **extra}
    return client.post(BASE + "/daily-notes/drafts", headers=teacher, json=data)


def note_list(client, teacher):
    return client.get(BASE + "/daily-notes", headers=teacher,
                      params={"classroom_id": str(seed.CLASS_STAR), "date": store.now().date().isoformat()})


def upload(client, headers, filename="새 안내.txt", content=b"new notice", **extra):
    data = {"doc_type": "notice", "visibility": "all", "effective_from": store.now().date().isoformat(), **extra}
    return client.post(BASE + "/documents", headers=headers, data=data, files={"file": (filename, content, "text/plain")})


def test_notes_batch_blocks_all_then_sends_once(client, teacher, parent, parent_other, director):
    created = draft(client, teacher)
    assert created.status_code == 202 and created.json()["draft_status"] == "succeeded"
    iid = created.json()["input_id"]
    status = client.get(f"{BASE}/daily-notes/drafts/{iid}", headers=teacher)
    assert status.status_code == 200 and status.json()["draft_status"] == "succeeded"
    assert draft(client, teacher, activities="다시 제출").status_code == 200
    assert len(store.state().note_inputs) == 1
    response = note_list(client, teacher)
    assert response.status_code == 200, response.text
    notes = response.json()["items"]
    assert len(notes) == 2 and {n["status"] for n in notes} == {"draft", "needs_check"}
    assert {x["key"] for x in notes[0]["content"]["items"]} == {"day", "meal", "supplies"}
    meal = next(x for x in notes[0]["content"]["items"] if x["key"] == "meal")
    assert meal["source"]["document_id"] == str(seed.MENU) and "카레라이스" in meal["value"]
    batch = {"classroom_id": str(seed.CLASS_STAR), "note_date": store.now().date().isoformat()}
    blocked = client.post(BASE + "/daily-notes/send", headers=teacher, json=batch)
    err(blocked, 409, "NOTE_BATCH_BLOCKED")
    assert len(blocked.json()["error"]["details"]["blocked"]) == 2
    assert all(n.status != "sent" for n in store.state().notes.values())
    for n in notes:
        checked = client.patch(f"{BASE}/daily-notes/{n['id']}", headers=teacher,
                               json={"resolved_checks": [c["id"] for c in n["open_checks"]], "confirm": True})
        assert checked.status_code == 200 and checked.json()["note"]["status"] == "ready"
    sent = client.post(BASE + "/daily-notes/send", headers=teacher, json=batch)
    assert sent.status_code == 200 and sent.json()["sent_count"] == 2
    assert client.post(BASE + "/daily-notes/send", headers=teacher, json=batch).json()["sent_count"] == 0
    for headers, child in ((parent, seed.CHILD), (parent_other, seed.demo_id("503"))):
        visible = client.get(BASE + "/daily-notes", headers=headers, params={"date": store.now().date().isoformat()}).json()
        assert visible["total"] == 1 and visible["items"][0]["child_id"] == str(child)
        assert visible["items"][0]["open_checks"] == []
        assert any(n["kind"] == "note_sent" and n["subject_type"] == "daily_note" for n in client.get(BASE + "/notifications", headers=headers).json()["items"])
    assert len([n for n in store.state().notifications.values() if n.kind == "note_sent"]) == 2
    err(client.post(BASE + "/daily-notes/send", headers=director, json=batch), 403, "FORBIDDEN_ROLE")
    assert client.get(BASE + "/daily-notes", headers=director, params={"date": store.now().date().isoformat()}).json()["total"] == 2


def test_patch_is_atomic_and_requires_all_checks(client, teacher, parent, teacher_other):
    assert draft(client, teacher).status_code == 202
    assert client.get(BASE + "/daily-notes", headers=parent, params={"date": store.now().date().isoformat()}).json()["items"] == []
    n = next(n for n in note_list(client, teacher).json()["items"] if n["status"] == "needs_check")
    original = store.state().notes[UUID(n["id"])].content
    content = {"items": [{"key": "day", "label": "오늘 하루", "value": "새 내용", "source": {"type": "teacher_input"}}]}
    err(client.patch(f"{BASE}/daily-notes/{n['id']}", headers=teacher, json={"confirm": True, "content": content}), 409, "INVALID_TRANSITION")
    assert store.state().notes[UUID(n["id"])].content == original
    err(client.patch(f"{BASE}/daily-notes/{n['id']}", headers=teacher, json={"resolved_checks": ["unknown"]}), 422, "VALIDATION_FAILED")
    err(client.patch(f"{BASE}/daily-notes/{n['id']}", headers=teacher_other, json={"confirm": True}), 404, "NOT_FOUND")
    err(client.patch(f"{BASE}/daily-notes/{n['id']}", headers=parent, json={"confirm": True}), 403, "FORBIDDEN_ROLE")
    patched = client.patch(f"{BASE}/daily-notes/{n['id']}", headers=teacher,
                           json={"confirm": True, "resolved_checks": ["c1"], "content": content})
    assert patched.status_code == 200 and patched.json()["note"]["content"]["items"][0]["value"] == "새 내용"


def test_concurrent_note_send_once(client, teacher):
    assert draft(client, teacher).status_code == 202
    for n in note_list(client, teacher).json()["items"]:
        assert client.patch(f"{BASE}/daily-notes/{n['id']}", headers=teacher,
                            json={"confirm": True, "resolved_checks": [c["id"] for c in n["open_checks"]]}).status_code == 200
    batch = {"classroom_id": str(seed.CLASS_STAR), "note_date": store.now().date().isoformat()}
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: client.post(BASE + "/daily-notes/send", headers=teacher, json=batch), range(2)))
    assert sorted(r.json()["sent_count"] for r in responses) == [0, 2]


def test_failed_note_and_document_jobs_are_queryable(client, teacher):
    note = draft(client, teacher, "[실패] 화면 확인")
    assert note.status_code == 202 and note.json()["draft_status"] == "failed"
    query = client.get(f"{BASE}/daily-notes/drafts/{note.json()['input_id']}", headers=teacher)
    assert query.status_code == 200 and query.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert note_list(client, teacher).json()["total"] == 0
    doc = upload(client, teacher, filename="[실패] 자료.txt")
    assert doc.status_code == 202, doc.text
    assert doc.json()["document"]["ingest_status"] == "failed"
    query = client.get(f"{BASE}/documents/{doc.json()['document']['id']}", headers=teacher)
    assert query.status_code == 200 and query.json()["document"]["error"]["code"] == "UPSTREAM_UNAVAILABLE"
    assert query.json()["document"]["chunk_count"] == 0
    assert len([e for e in store.state().events if e.action == "tool_failed"]) == 2


def test_document_upload_duplicate_replacement_and_scope(client, teacher, teacher_other, director, parent):
    first = upload(client, teacher, content="새 식단 자료".encode(), **{"classroom_ids[]": str(seed.CLASS_STAR)})
    assert first.status_code == 202 and first.json()["document"]["chunk_count"] == 1, first.text
    document = first.json()["document"]
    assert document["classroom_ids"] == [str(seed.CLASS_STAR)]
    duplicate = upload(client, teacher, filename="이름만 다름.txt", content="새 식단 자료".encode())
    assert duplicate.status_code == 200 and duplicate.json()["document"]["id"] == document["id"]
    err(client.get(f"{BASE}/documents/{document['id']}", headers=teacher_other), 404, "NOT_FOUND")
    listed = client.get(BASE + "/documents", headers=teacher_other).json()
    assert document["id"] not in [d["id"] for d in listed["items"]]
    newer = upload(client, director, content=b"new revision", replaces_document_id=document["id"])
    assert newer.status_code == 202 and newer.json()["document"]["supersedes_id"] == document["id"]
    assert client.get(f"{BASE}/documents/{document['id']}", headers=teacher).json()["document"]["status"] == "superseded"
    err(upload(client, director, content=b"invalid fork", replaces_document_id=document["id"]), 409, "INVALID_TRANSITION")
    err(upload(client, teacher, **{"classroom_ids[]": str(seed.CLASS_SUN)}), 404, "NOT_FOUND")
    err(upload(client, parent), 403, "FORBIDDEN_ROLE")
    err(upload(client, teacher, doc_type="invalid"), 422, "VALIDATION_FAILED")
    err(upload(client, teacher, effective_from="bad-date"), 422, "VALIDATION_FAILED")
    assert client.get(BASE + "/documents?size=1&page=2", headers=director).json()["page"] == 2


def test_sources_hide_staff_docs_and_warn_on_stale_evidence(client, parent, teacher):
    rid, cid = create(client, parent, type="inquiry", body="식단이 궁금해요")
    card = store.state().cards[UUID(cid)]
    old_chunk = next(c for c in store.state().chunks.values() if c.document_id == seed.OLD_NOTICE)
    store.state().evidence.append(Evidence(card.id, card.org_id, old_chunk.id, 2, "옛 내용"))
    card.draft["law_unchecked"] = True
    card.check_result = None
    detail = client.get(f"{BASE}/cards/{cid}", headers=teacher)
    assert detail.status_code == 200, detail.text
    assert {"stale_evidence", "law_unchecked", "check_unavailable"}.issubset(detail.json()["warnings"])
    store.state().documents[seed.MENU].visibility = "staff"
    assert decision(client, teacher, cid).status_code == 200
    detail = client.get(f"{BASE}/requests/{rid}", headers=parent).json()
    assert all(s["document_title"] != "가상 식단표" for s in detail["sources"])
    assert "risk_level" not in detail["request"]
    assert all(set(t) == {"label", "at"} for t in detail["timeline"])
    assert all(set(s) == {"document_title", "location", "effective_from"} for s in detail["sources"])


def test_daily_note_validation_and_foreign_scope(client, teacher, teacher_other, director):
    future = (store.now().date() + timedelta(days=1)).isoformat()
    err(draft(client, teacher, note_date=future), 422, "VALIDATION_FAILED")
    err(draft(client, teacher_other), 404, "NOT_FOUND")
    err(draft(client, director), 403, "FORBIDDEN_ROLE")
    entry = draft(client, teacher).json()
    err(client.get(f"{BASE}/daily-notes/drafts/{entry['input_id']}", headers=teacher_other), 404, "NOT_FOUND")
    err(client.get(BASE + "/daily-notes", headers=teacher, params={"date": store.now().date().isoformat()}), 422, "VALIDATION_FAILED")
    err(client.get(BASE + "/daily-notes", headers=teacher_other,
                   params={"date": store.now().date().isoformat(), "classroom_id": str(seed.CLASS_STAR)}), 404, "NOT_FOUND")


@pytest.mark.parametrize("mutation", ["expired", "version", "inactive", "org", "role", "signature"])
def test_auth_rejects_invalid_claims(client, mutation):
    user = store.get_user(seed.TEACHER)
    token = issue_token(user)
    claims = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if mutation == "expired":
        claims["exp"] = 0
    elif mutation == "version":
        user.token_version += 1
    elif mutation == "inactive":
        user.is_active = False
    elif mutation == "org":
        claims["org"] = str(uuid4())
    elif mutation == "role":
        claims["role"] = "director"
    key = "wrong-signature-key-32-characters-long" if mutation == "signature" else settings.jwt_secret
    token = jwt.encode(claims, key, algorithm="HS256")
    err(client.get(BASE + "/me", headers={"Authorization": "Bearer " + token}), 401, "UNAUTHENTICATED")


def test_other_org_and_expired_teacher_assignment(client, teacher, monkeypatch):
    from app.mock import cards
    user = store.get_user(seed.TEACHER)
    other_org = uuid4()
    card = store.state().cards[seed.CARD_COMPLAINT]
    card.org_id = other_org
    err(client.get(f"{BASE}/cards/{card.id}", headers=teacher), 404, "NOT_FOUND")
    card.org_id = seed.ORG
    for assignment in store.state().classroom_staff:
        if assignment.user_id == user.id:
            assignment.valid_to = store.now().date() - timedelta(days=1)
    card.assignee_id = seed.TEACHER_OTHER
    err(client.get(f"{BASE}/cards/{card.id}", headers=teacher), 404, "NOT_FOUND")
