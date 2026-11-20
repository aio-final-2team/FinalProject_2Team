"""알림장 v0.4: 아이별 메모·확인 항목·반 아이 목록의 공개 계약."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from app.api.schemas.views import OpenCheck
from app.main import app
from app.mock import seed, store
from tests.integration.api.helpers import BASE, err
from tests.integration.api.test_resources import draft, note_list


@pytest.mark.parametrize("memo", ["", "가" * 501])
def test_child_memo_length_rejected_without_writes(client, teacher, memo):
    response = draft(client, teacher, child_memos=[{"child_id": str(seed.CHILD), "memo": memo}])
    err(response, 422, "VALIDATION_FAILED")
    assert not store.state().note_inputs and not store.state().notes


def test_duplicate_child_memos_rejected_without_writes(client, teacher):
    memo = {"child_id": str(seed.CHILD), "memo": "블록 놀이"}
    response = draft(client, teacher, child_memos=[memo, {**memo, "memo": "산책"}])
    err(response, 422, "VALIDATION_FAILED")
    assert not store.state().note_inputs and not store.state().notes


@pytest.mark.parametrize("outside", ["other_class", "other_org", "missing"])
def test_child_memo_outside_class_has_id_and_no_partial_write(client, teacher, outside):
    child_id = seed.CHILD_OTHER if outside == "other_class" else uuid4()
    if outside == "other_org":
        store.state().children[child_id] = store.Child(child_id, uuid4(), seed.CLASS_STAR, "다른 기관", [])
    cards_before = set(store.state().cards)
    response = draft(client, teacher, child_memos=[
        {"child_id": str(seed.CHILD), "memo": "정상 메모"},
        {"child_id": str(child_id), "memo": "범위 밖 메모"},
    ])
    err(response, 422, "VALIDATION_FAILED")
    assert response.json()["error"]["details"]["child_id"] == str(child_id)
    assert not store.state().note_inputs and not store.state().notes
    assert set(store.state().cards) == cards_before


@pytest.mark.parametrize("memo", ["탑 쌓기", "가" * 500])
def test_memo_is_copied_only_to_its_child_and_patch_keeps_contract(client, teacher, memo):
    response = draft(client, teacher, child_memos=[
        {"child_id": str(seed.CHILD), "memo": memo},
        {"child_id": str(seed.demo_id("503")), "memo": " \t "},
    ])
    assert response.status_code == 202, response.text
    listed = note_list(client, teacher)
    assert listed.status_code == 200, listed.text
    notes = listed.json()["items"]
    assert len(notes) == 20
    child_note = next(note for note in notes if note["child_id"] == str(seed.CHILD))
    for note in notes:
        lines = [line for line in note["content"]["items"] if line["key"] == "child"]
        if note == child_note:
            assert len(lines) == 1 and lines[0]["value"] == memo
            assert lines[0]["source"]["type"] == "teacher_input"
        else:
            assert lines == []
    # 모의 저장소에도 입력을 남기고, 같은 반·날짜 재접수는 처음 입력을 유지해요.
    entry = store.state().note_inputs[UUID(response.json()["input_id"])]
    assert entry.child_memos[0] == {"child_id": seed.CHILD, "memo": memo}
    assert draft(client, teacher, child_memos=[{"child_id": str(seed.CHILD), "memo": "재접수"}]).status_code == 200
    assert entry.child_memos[0]["memo"] == memo
    patch = client.patch(f"{BASE}/daily-notes/{child_note['id']}", headers=teacher,
                         json={"content": child_note["content"],
                               "resolved_checks": [check["id"] for check in child_note["open_checks"]],
                               "confirm": True})
    assert patch.status_code == 200 and patch.json()["note"]["status"] == "ready"
    assert patch.json()["note"]["open_checks"] == []


@pytest.mark.parametrize("extra", [{}, {"child_memos": []}])
def test_omitted_or_empty_memos_add_no_child_line(client, teacher, extra):
    assert draft(client, teacher, **extra).status_code == 202
    assert all(line["key"] != "child" for note in note_list(client, teacher).json()["items"]
               for line in note["content"]["items"])


def test_open_check_has_seven_kinds_required_kind_and_nullable_sentence(client, teacher):
    schema = app.openapi()["components"]["schemas"]["OpenCheck"]
    assert set(schema["properties"]["kind"]["enum"]) == {
        "not_in_memo", "sensitive", "other_child", "date_check", "absent", "draft_failed", "check_failed"}
    assert "kind" in schema["required"]
    check = {"id": "c1", "item_key": "child", "problem": "메모를 확인해 주세요"}
    with pytest.raises(ValidationError):
        OpenCheck.model_validate(check)
    with pytest.raises(ValidationError):
        OpenCheck.model_validate({**check, "kind": "unknown"})
    assert OpenCheck.model_validate({**check, "kind": "check_failed"}).sentence is None
    assert draft(client, teacher).status_code == 202
    checks = [check for note in note_list(client, teacher).json()["items"] for check in note["open_checks"]]
    assert checks == [{"id": "c1", "item_key": "supplies", "kind": "date_check",
                       "problem": "준비물 날짜를 확인해 주세요", "sentence": "내일 실내화"}]


def test_child_line_rejects_non_teacher_source(client, teacher):
    assert draft(client, teacher).status_code == 202
    note = note_list(client, teacher).json()["items"][0]
    content = {"items": [{"key": "child", "label": "아이 메모", "value": "메모",
                          "source": {"type": "document", "document_id": str(seed.MENU), "document_title": "식단"}}]}
    err(client.patch(f"{BASE}/daily-notes/{note['id']}", headers=teacher, json={"content": content}),
        422, "VALIDATION_FAILED")


def test_classroom_children_sorted_complete_and_director_allowed(client, teacher, teacher_other, director):
    url = f"{BASE}/classrooms/{seed.CLASS_STAR}/children"
    response = client.get(url, headers=teacher)
    assert response.status_code == 200, response.text
    children = response.json()["items"]
    assert len(children) == 20
    assert [child["display_name"] for child in children] == sorted(child["display_name"] for child in children)
    assert {child["id"] for child in children} == {
        str(child["id"]) for child in seed.CHILDREN if child["classroom_id"] == seed.CLASS_STAR}
    assert all(set(child) == {"id", "display_name", "classroom_id"} for child in children)
    assert all(child["classroom_id"] == str(seed.CLASS_STAR) for child in children)
    assert client.get(url, headers=director).json() == response.json()
    other_url = f"{BASE}/classrooms/{seed.CLASS_SUN}/children"
    assert client.get(other_url, headers=teacher_other).json() == {"items": [
        {"id": str(seed.CHILD_OTHER), "display_name": "바다", "classroom_id": str(seed.CLASS_SUN)}]}


def test_classroom_children_role_scope_and_auth(client, teacher, teacher_other, parent, director):
    url = f"{BASE}/classrooms/{seed.CLASS_STAR}/children"
    err(client.get(url), 401, "UNAUTHENTICATED")
    err(client.get(url, headers=parent), 403, "FORBIDDEN_ROLE")
    err(client.get(url, headers=teacher_other), 404, "NOT_FOUND")
    err(client.get(f"{BASE}/classrooms/{uuid4()}/children", headers=director), 404, "NOT_FOUND")
    store.state().classrooms[seed.CLASS_STAR].org_id = uuid4()
    err(client.get(url, headers=director), 404, "NOT_FOUND")
    err(client.get(url, headers=teacher), 404, "NOT_FOUND")


@pytest.mark.parametrize("period,allowed", [("expired", False), ("future", False), ("today", True)])
def test_classroom_children_assignment_period(client, teacher, period, allowed):
    today = store.now().date()
    assignment = next(s for s in store.state().classroom_staff if s.user_id == seed.TEACHER)
    if period == "expired":
        assignment.valid_to = today - timedelta(days=1)
    elif period == "future":
        assignment.valid_from = today + timedelta(days=1)
    else:
        assignment.valid_from = assignment.valid_to = today
    response = client.get(f"{BASE}/classrooms/{seed.CLASS_STAR}/children", headers=teacher)
    if allowed:
        assert response.status_code == 200
    else:
        err(response, 404, "NOT_FOUND")


def test_seed_names_roster_order_and_guardians():
    assert [(c["id"], c["name"]) for c in seed.CLASSROOMS] == [
        (seed.CLASS_STAR, "만 4세 별빛반"), (seed.CLASS_SUN, "만 5세 햇님반")]
    assert [(u["login_id"], u["display_name"]) for u in seed.USERS[:2]] == [
        ("teacher01", "별빛반 선생님"), ("teacher02", "햇님반 선생님")]
    roster = [child for child in seed.CHILDREN if not child["guardian_ids"]]
    assert [child["display_name"] for child in roster] == [
        "가온", "나래", "다온", "라온", "마루", "별하", "새봄", "아라", "여름",
        "윤슬", "이든", "지아", "지안", "채온", "하람", "한결", "해든", "로아"]
    assert [child["id"] for child in roster] == [seed.demo_id(f"54{number:02d}") for number in range(1, 19)]
    assert all(child["classroom_id"] == seed.CLASS_STAR for child in roster)
    assert len(seed.CHILDREN) == 21
    assert sum(child["classroom_id"] == seed.CLASS_STAR for child in seed.CHILDREN) == 20
    assert sum(child["classroom_id"] == seed.CLASS_SUN for child in seed.CHILDREN) == 1
    assert {child["id"] for child in seed.CHILDREN}.isdisjoint(
        seed.demo_id(f"55{number:02d}") for number in range(1, 19))
    assert [(c["display_name"], c["guardian_ids"]) for c in seed.CHILDREN[:3]] == [
        ("하늘", [seed.PARENT]), ("바다", [seed.PARENT_OTHER]), ("노을", [seed.PARENT_OTHER])]
