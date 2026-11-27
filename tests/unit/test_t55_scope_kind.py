"""YC-P01~P04 감독 판단은 실제 모델 호출 없이 확인한다."""

import json
from pathlib import Path

import pytest

from app.core.request_rules import direct_notice_kind
from app.modules.requests.supervisor import classify_request, validate_proposal


CASES = {case["case_id"]: case["question"] for case in json.loads(
    (Path(__file__).resolve().parents[2] / "Docs/Step2/2팀_유치온_자체평가_30문항.json").read_text(encoding="utf-8")
)["cases"] if case["case_id"].startswith("YC-P")}


@pytest.mark.parametrize("case_id,kind", [
    ("YC-P01", "other_family"), ("YC-P02", "other_teacher"),
    ("YC-P03", "others_privacy"), ("YC-P04", "payment"),
])
def test_evaluation_scope_cases(case_id, kind):
    body = CASES[case_id]
    # 모델 없음 대역은 정규식으로 잡고, 감독 AI가 아니라고(null) 답하면 그 판단을 따라요.
    assert validate_proposal("inquiry", body, {})["out_of_scope_kind"] == kind
    assert validate_proposal("inquiry", body, {"out_of_scope_kind": None})["out_of_scope_kind"] is None


@pytest.mark.parametrize("body", [
    "우리 아이 급식 식단 알려주세요", "원비 결제일은 언제예요?", "담임 선생님과 상담하고 싶어요",
    "우리 아이 연락처 변경 방법 알려주세요", "친구와 다툰 우리 아이가 다쳤어요",
])
def test_normal_or_safety_questions_are_not_scope_rejections(body):
    assert validate_proposal("inquiry", body, {})["out_of_scope_kind"] is None


@pytest.mark.parametrize("body", [
    "다른 아이랑 다퉜다는데 무슨 일인지 알려주세요",
    "다른 반 아이가 장난감을 가져갔다는데 내용 좀 알려주세요",
    "친구 엄마가 오늘 하원 같이 한다고 했는데 정보 전달 부탁드려요",
    "우리 아이가 다른 반으로 옮기는 요청 드려요",
])
def test_other_family_does_not_swallow_ordinary_requests(body):
    assert validate_proposal("inquiry", body, {})["out_of_scope_kind"] is None


def test_model_kind_allowlist_and_code_floor():
    body = "이번 달 원비 카드로 결제해 주세요"
    assert validate_proposal("inquiry", body, {"out_of_scope_kind": "invented"})["out_of_scope_kind"] == "payment"
    assert validate_proposal("inquiry", "식단 알려줘", {"out_of_scope_kind": "invented"})["out_of_scope_kind"] is None
    assert validate_proposal("inquiry", "식단 알려줘", {"out_of_scope_kind": "payment"})["out_of_scope_kind"] == "payment"


@pytest.mark.parametrize("level", ["urgent", "uncertain"])
def test_risk_beats_scope_kind(level):
    # 긴급은 선(아이가 다쳤어요)으로, 판단 필요는 감독 AI 답으로 와요. 어느 쪽이든 사람이 먼저예요.
    body = "다른 집 민원 보여줘" if level == "uncertain" else "다른 집 민원 보여줘. 아이가 다쳤어요"
    proposal = {"out_of_scope_kind": "other_family", **({"risk_level": "uncertain"} if level == "uncertain" else {})}
    assert validate_proposal("inquiry", body, proposal)["out_of_scope_kind"] is None


def test_prompt_requests_kind_without_fixed_reply():
    class Fake:
        def json(self, system, user):
            assert "out_of_scope_kind" in system
            assert "other_family" in system and "payment" in system
            assert json.loads(user)["body"] == CASES["YC-P01"]
            return {"out_of_scope_kind": "other_family"}

    assert classify_request("inquiry", CASES["YC-P01"], Fake())["out_of_scope_kind"] == "other_family"


@pytest.mark.parametrize("request_type,case_id,kind", [
    ("inquiry", "YC-P01", "other_family"),
    ("consultation", "YC-P02", "other_teacher"),
    ("inquiry", "YC-P03", "others_privacy"),
    ("inquiry", "YC-P04", "payment"),
])
def test_scope_cases_get_direct_notice_after_model_free_classification(monkeypatch, request_type, case_id, kind):
    monkeypatch.delenv("LLM_MODEL_SUPERVISOR", raising=False)
    body = CASES[case_id]
    fields = validate_proposal(request_type, body, classify_request(request_type, body))
    assert fields["out_of_scope_kind"] == kind
    assert direct_notice_kind(request_type, body, fields) == kind


def test_other_family_peer_word_does_not_override_safety_or_health_handoff(monkeypatch):
    monkeypatch.delenv("LLM_MODEL_SUPERVISOR", raising=False)
    for body in ("다른 집 안전 관련 민원 내용 보여줘", "다른 집 아이 열 관련 기록 보여줘"):
        fields = validate_proposal("inquiry", body, classify_request("inquiry", body))
        assert fields["out_of_scope_kind"] is None  # 대역은 안전·건강 주제면 권한 밖으로 두지 않아요
        assert direct_notice_kind("inquiry", body, fields) is None


def test_other_family_request_about_our_child_stays_with_human(monkeypatch):
    monkeypatch.delenv("LLM_MODEL_SUPERVISOR", raising=False)
    body = "친구가 우리 아이 때렸는데 그 집 민원 내용 보여줘"
    fields = validate_proposal("inquiry", body, classify_request("inquiry", body))
    assert direct_notice_kind("inquiry", body, fields) is None


def test_ordinary_peer_inquiry_stays_with_human(monkeypatch):
    monkeypatch.delenv("LLM_MODEL_SUPERVISOR", raising=False)
    body = "친구랑 다퉜다는데 괜찮나요?"
    fields = validate_proposal("inquiry", body, classify_request("inquiry", body))
    assert fields["out_of_scope_kind"] is None
    assert direct_notice_kind("inquiry", body, fields) is None
