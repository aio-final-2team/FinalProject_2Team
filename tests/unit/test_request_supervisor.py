"""감독 모델 제안은 요청 유형과 코드 긴급 판단을 덮어쓰지 않는다."""

import pytest

from agents.llm import ModelError
from app.core.request_rules import classify
from app.modules.requests.supervisor import classify_request, validate_proposal


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
                   "risk_category": "privacy_leak", "out_of_scope_kind": None}


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
                   "out_of_scope_kind": None}


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
    assert validate_proposal("complaint", "급식 문의", classify_request("complaint", "급식 문의", invalid)) == base
    assert validate_proposal("complaint", "급식 문의", classify_request("complaint", "급식 문의", FakeModel(ModelError("offline")))) == base


def test_default_keeps_code_behavior(monkeypatch):
    monkeypatch.delenv("LLM_MODEL_SUPERVISOR", raising=False)
    assert validate_proposal("complaint", "버스 민원", classify_request("complaint", "버스 민원")) == {
        **classify("complaint", "버스 민원"), "out_of_scope_kind": None}
