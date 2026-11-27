"""감독 AI 판단이 계약 목록 안이면 그대로 쓴다. 코드는 요청 유형·선(아이 몸에 해가 간 표현)만 지키고, 낱말은 모델 없음 대역이다."""

import pytest

from agents.llm import ModelError
from app.core.request_rules import classify
from app.modules.requests.supervisor import PROMPTS, classify_request, validate_proposal


class FakeModel:
    def __init__(self, result):
        self.result = result
        self.inputs = []

    def json(self, system, user):
        self.inputs.append((system, user))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_supervisor_adds_topic_and_risk(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_SUPERVISOR", "fake-model")
    model = FakeModel({"type": "complaint", "topic_key": "meal", "urgency": "normal",
                       "risk_level": "uncertain", "risk_category": "privacy_leak"})
    got = validate_proposal("complaint", "급식이 차가워요", classify_request("complaint", "급식이 차가워요", model))
    assert got == {"topic_key": "meal", "urgency": "normal", "risk_level": "uncertain",
                   "risk_category": "privacy_leak", "out_of_scope_kind": None, "intent": "ask"}


def test_screen_type_is_fixed_and_code_urgency_cannot_be_weakened(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_SUPERVISOR", "fake-model")
    model = FakeModel({"type": "inquiry", "topic_key": "safety", "urgency": "normal",
                       "risk_level": "normal", "risk_category": None})
    got = validate_proposal("complaint", "아이가 다쳤어요", classify_request("complaint", "아이가 다쳤어요", model))
    assert got["urgency"] == "urgent" and got["risk_level"] == "urgent"
    assert got["risk_category"] == "child_safety"
    assert "complaint" in model.inputs[0][1]


def test_care_request_does_not_accept_model_risk(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_SUPERVISOR", "fake-model")
    got = validate_proposal("medication", "식단 문의", classify_request("medication", "식단 문의", FakeModel({
        "topic_key": "meal", "urgency": "urgent", "risk_level": "urgent",
        "risk_category": "child_safety"})))
    assert got["topic_key"] == "meal" and got["urgency"] == "urgent"
    assert "risk_level" not in got and "risk_category" not in got


@pytest.mark.parametrize("request_type", ["inquiry", "consultation"])
def test_inquiry_and_consultation_accept_model_risk_like_complaint(monkeypatch, request_type):
    monkeypatch.setenv("LLM_MODEL_SUPERVISOR", "fake-model")
    model = FakeModel({"topic_key": "meal", "urgency": "normal", "risk_level": "urgent",
                       "risk_category": "child_safety"})
    got = validate_proposal(request_type, "식단 문의", classify_request(request_type, "식단 문의", model))
    assert got == {"topic_key": "meal", "urgency": "urgent", "risk_level": "urgent", "risk_category": "child_safety",
                   "out_of_scope_kind": None, "intent": "ask"}


def test_urgent_risk_without_category_becomes_uncertain():
    got = validate_proposal("complaint", "확인 필요", {
        "topic_key": "other", "urgency": "normal", "risk_level": "urgent", "risk_category": None,
    })
    assert got["risk_level"] == "uncertain" and got["risk_category"] is None


def test_bad_values_and_model_failure_fall_back_to_code(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_SUPERVISOR", "fake-model")
    invalid = FakeModel({"topic_key": "invented", "urgency": "critical", "risk_level": "safe",
                         "risk_category": "made_up"})
    base = {**classify("complaint", "급식 문의"), "out_of_scope_kind": None}
    base["intent"] = "ask"
    assert validate_proposal("complaint", "급식 문의", classify_request("complaint", "급식 문의", invalid)) == base
    assert validate_proposal("complaint", "급식 문의", classify_request("complaint", "급식 문의", FakeModel(ModelError("offline")))) == base


def test_default_keeps_code_behavior(monkeypatch):
    monkeypatch.delenv("LLM_MODEL_SUPERVISOR", raising=False)
    assert validate_proposal("complaint", "버스 민원", classify_request("complaint", "버스 민원")) == {
        **classify("complaint", "버스 민원"), "out_of_scope_kind": None, "intent": "ask"}


@pytest.mark.parametrize("intent", ["notice", "ask"])
def test_inquiry_accepts_only_supported_intent(intent):
    got = validate_proposal("inquiry", "오후에 확인해 주세요", {"intent": intent})
    assert got["intent"] == intent


@pytest.mark.parametrize("intent", [None, "invented", "NOTICE"])
def test_invalid_or_missing_intent_defaults_to_ask(intent):
    got = validate_proposal("inquiry", "금요일엔 외삼촌이 데리러 갈 예정입니다", {"intent": intent})
    assert got["intent"] == "ask"


@pytest.mark.parametrize("request_type", ["consultation", "complaint", "medication", "pickup"])
@pytest.mark.parametrize("intent", ["notice", "ask", "invented", None])
def test_non_inquiry_intent_is_always_ask(request_type, intent):
    got = validate_proposal(request_type, "내용", {"intent": intent})
    assert got["intent"] == "ask"


def test_inquiry_model_failure_and_non_dict_default_to_ask(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_SUPERVISOR", "fake-model")
    assert validate_proposal("inquiry", "안내해 주세요", classify_request(
        "inquiry", "안내해 주세요", FakeModel(ModelError("offline"))))["intent"] == "ask"
    assert validate_proposal("inquiry", "안내해 주세요", [])["intent"] == "ask"


@pytest.mark.parametrize("category", ["health", None, "건강"])
def test_inquiry_model_uncertain_without_known_category_is_kept(category):
    # 건강 문의를 일반으로 내리던 코드 예외는 없앴어요. 판단 필요 기준은 supervisor.md 원칙으로 AI에게 줘요.
    body = "아이가 열이 나면 등원해도 되나요?"
    got = validate_proposal("inquiry", body, {"topic_key": "health_hygiene", "urgency": "normal",
                                               "risk_level": "uncertain", "risk_category": category})
    assert got["risk_level"] == "uncertain" and got["risk_category"] is None


def test_inquiry_model_uncertain_with_known_category_is_kept():
    got = validate_proposal("inquiry", "아이 몸에 못 보던 상처가 있는데 원에서 무슨 일 있었나요?", {
        "topic_key": "safety", "urgency": "normal", "risk_level": "uncertain", "risk_category": "child_safety"})
    assert got["risk_level"] == "uncertain" and got["risk_category"] == "child_safety"


def test_inquiry_model_urgent_without_known_category_still_goes_to_people():
    got = validate_proposal("inquiry", "원에서 무슨 일이 있었던 것 같아요", {
        "topic_key": "other", "urgency": "urgent", "risk_level": "urgent", "risk_category": "safety"})
    assert got["risk_level"] == "uncertain"


@pytest.mark.parametrize("request_type", ["complaint", "consultation"])
def test_other_types_keep_model_uncertain_without_category(request_type):
    got = validate_proposal(request_type, "요즘 원에 보내기가 걱정돼요", {
        "topic_key": "other", "urgency": "normal", "risk_level": "uncertain", "risk_category": None})
    assert got["risk_level"] == "uncertain"


def test_inquiry_with_judgement_phrase_in_body_is_kept():
    got = validate_proposal("inquiry", "판단 필요한 문의예요", {
        "topic_key": "other", "urgency": "normal", "risk_level": "uncertain", "risk_category": None})
    assert got["risk_level"] == "uncertain"


def test_model_topic_and_normal_risk_beat_fallback_words():
    # 낱말 대역이면 '선생님'→teacher, '변호사'→긴급이지만, AI가 목록 안 값을 주면 그대로 써요.
    body = "[TEST] 변호사 선생님 상담이 있어서 일찍 하원해요"
    assert classify("inquiry", body)["risk_level"] == "urgent"
    got = validate_proposal("inquiry", body, {"topic_key": "pickup_bus", "urgency": "normal",
                                               "risk_level": "normal", "risk_category": "legal_external"})
    assert (got["topic_key"], got["risk_level"], got["risk_category"], got["urgency"]) == (
        "pickup_bus", "normal", None, "normal")


@pytest.mark.parametrize("level", ["normal", "uncertain"])
def test_child_harm_line_raises_model_risk(level):
    got = validate_proposal("complaint", "[TEST] 아이가 친구에게 맞고 왔어요", {"topic_key": "peer_conflict",
                            "risk_level": level, "risk_reason": "[TEST] 이유"})
    assert (got["risk_level"], got["risk_category"], got["urgency"]) == ("urgent", "child_safety", "urgent")
    assert "risk_reason" not in got


def test_risk_reason_is_one_masked_line_only_for_uncertain():
    reason = "  [TEST] 교직원을   탓하는지\n애매해요 010-1234-5678 " + "가" * 100
    got = validate_proposal("complaint", "[TEST] 급식 민원", {"risk_level": "uncertain", "risk_reason": reason})
    assert got["risk_reason"].startswith("[TEST] 교직원을 탓하는지 애매해요 [전화번호] 가")
    assert len(got["risk_reason"]) == 80 and "\n" not in got["risk_reason"]
    for level in ("normal", "urgent"):
        assert "risk_reason" not in validate_proposal("complaint", "[TEST] 급식 민원", {
            "risk_level": level, "risk_category": "staff_attack", "risk_reason": "[TEST] 이유"})
    assert "risk_reason" not in validate_proposal("complaint", "[TEST] 급식 민원", {"risk_level": "uncertain", "risk_reason": 3})


def test_prompt_asks_for_risk_reason_without_tool_flow(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_SUPERVISOR", "fake-model")
    model = FakeModel({})
    classify_request("complaint", "[TEST] 급식 민원", model)
    assert "risk_reason" in model.inputs[0][0] and "3건째" in model.inputs[0][0]
    # 코드는 분류 JSON만 받으므로 감독 지침에 도구 흐름·채워지지 않는 자리표시를 두지 않아요.
    prompt = (PROMPTS / "supervisor.md").read_text(encoding="utf-8")
    assert not any(tool in prompt for tool in ("search_documents", "find_consult_slots", "create_card", "get_my_requests", "{"))
