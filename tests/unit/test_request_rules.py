"""위험 낱말 표: 평범한 문의는 일반, 위험한 글은 문의·상담·민원 모두 같은 등급이에요."""

import pytest

from app.core.constants import notification_title
from app.core.request_rules import classify

RISK_TYPES = ("inquiry", "consultation", "complaint")


@pytest.mark.parametrize("body,risk,category", [
    # 낱말 하나로 보던 때 긴급으로 잘못 걸리던 평범한 문의
    ("현장체험 안전 수칙 알려 주세요", "normal", None),
    ("결석 신고는 어떻게 해요?", "normal", None),
    ("개인정보 동의서는 어디에 내요?", "normal", None),
    # 낱말 하나로 보던 때 놓치던 법적 조치
    ("경찰에 알릴 거예요", "urgent", "legal_external"),
    ("소송 걸겠습니다", "urgent", "legal_external"),
    # 기존 시험·시드 본문은 등급이 그대로예요
    ("[TEST] 아이가 다쳤어요", "urgent", "child_safety"),
    ("선생님이 아이를 때렸다고 해요", "urgent", "child_safety"),
    ("아이 안전을 확인해 주세요", "urgent", "child_safety"),
    ("[TEST] 가만두지 않겠어요", "urgent", "staff_attack"),
    ("[TEST] 변호사에게 물었어요", "urgent", "legal_external"),
    ("[TEST] 개인정보 유출", "urgent", "privacy_leak"),
    ("[TEST] 개인정보가 유출됐어요", "urgent", "privacy_leak"),
    ("[TEST] 판단 필요 민원이에요", "uncertain", None),
    ("급식 관련 판단 필요 민원", "uncertain", None),
    ("등원 버스가 늦었어요", "normal", None),
])
@pytest.mark.parametrize("request_type", RISK_TYPES)
def test_risk_words_by_phrase_for_every_guardian_request_type(request_type, body, risk, category):
    got = classify(request_type, body)
    assert (got["risk_level"], got["risk_category"]) == (risk, category)
    assert got["urgency"] == ("urgent" if risk == "urgent" else "normal")


@pytest.mark.parametrize("request_type", ["medication", "pickup"])
def test_care_requests_have_no_risk_level(request_type):
    got = classify(request_type, "어제 다친 무릎에 연고 한 번 발라 주세요")
    assert "risk_level" not in got and "risk_category" not in got and got["urgency"] == "normal"


@pytest.mark.parametrize("kind,request_type,title", [
    ("urgent_complaint", "complaint", "긴급 민원"),
    ("urgent_complaint", "inquiry", "긴급 문의"),
    ("urgent_complaint", "consultation", "긴급 상담"),
    ("uncertain_complaint", "inquiry", "AI 판단 불확실 문의"),
    ("uncertain_complaint", None, "AI 판단 불확실 민원"),
    ("new_card", "inquiry", "새 카드가 왔어요"),
])
def test_risk_notice_title_names_request_type_but_kind_stays(kind, request_type, title):
    assert notification_title(kind, request_type) == title
