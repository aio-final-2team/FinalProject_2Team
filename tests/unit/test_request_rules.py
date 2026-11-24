"""위험 낱말 표: 평범한 문의는 일반, 위험한 글은 문의·상담·민원 모두 같은 등급이에요. 민원은 낱말 하나도 봐요."""

import pytest

from app.core.constants import notification_title
from app.core.request_rules import classify

RISK_TYPES = ("inquiry", "consultation", "complaint")


@pytest.mark.parametrize("body,category", [
    # 낱말 하나로 보면 긴급으로 잘못 걸리던 평범한 문의 — 문의·상담은 일반, 민원은 예전 그대로 긴급
    ("현장체험 안전 수칙 알려 주세요", "child_safety"),
    ("결석 신고는 어떻게 해요?", "legal_external"),
    ("개인정보 동의서는 어디에 내요?", "privacy_leak"),
    # 민원에서 예전처럼 잡아야 하는 글
    ("구청에 신고합니다", "legal_external"),
    ("우리 아이 개인정보를 단톡방에 올리셨어요", "privacy_leak"),
    ("버스에서 안전벨트를 안 채워 줬어요", "child_safety"),
    ("경찰에서 오는 교통안전 교육은 언제예요?", "child_safety"),  # '경찰에서'는 법적 조치가 아니에요
])
@pytest.mark.parametrize("request_type", RISK_TYPES)
def test_single_words_count_only_for_complaints(request_type, body, category):
    got = classify(request_type, body)
    expected = ("urgent", category) if request_type == "complaint" else ("normal", None)
    assert (got["risk_level"], got["risk_category"]) == expected


@pytest.mark.parametrize("body,risk,category", [
    # 낱말 하나로 보던 때 놓치던 법적 조치
    ("경찰에 알릴 거예요", "urgent", "legal_external"),
    ("소송 걸겠습니다", "urgent", "legal_external"),
    # 기존 시험·시드 본문은 등급이 그대로예요
    ("[TEST] 아이가 다쳤어요", "urgent", "child_safety"),
    ("선생님이 아이를 때렸다고 해요", "urgent", "child_safety"),
    ("아이 안전을 확인해 주세요", "urgent", "child_safety"),
    # 팀 서버에서 일반 민원으로 빠졌던 글(11/24)
    ("아이가 오늘 선생님한테 맞았다고 하고 팔에 멍이 들었어요", "urgent", "child_safety"),
    ("친구에게 맞고 왔어요", "urgent", "child_safety"),
    ("다리에 멍들어 왔어요", "urgent", "child_safety"),
    ("선생님이 아이를 꼬집었대요", "urgent", "child_safety"),
    # 평범한 글은 그대로예요
    ("독감 주사 맞았어요. 오늘 등원해도 되나요?", "normal", None),
    ("하원 시간이 맞았으면 좋겠어요", "normal", None),
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


@pytest.mark.parametrize("body,topic,expected", [
    # 팀 서버에서 담임 카드로 빠졌던 글(11/24): '친구' 때문에 또래 주제로 잡혀도 남의 연락처는 바로 안내해요
    ("옆 반 친구 엄마 전화번호 좀 알려 주세요", "peer_conflict", "others_privacy"),
    # 아이가 다친 일·아픈 일이 섞이면 사람이 봐요
    ("친구 엄마 전화번호 알려 주세요. 아이가 다쳤어요", "safety", None),
    ("우리 아이가 친구랑 다퉜어요. 친구 엄마 전화번호 알려 주세요", "peer_conflict", None),
])
def test_other_family_contact_request_gets_direct_notice(body, topic, expected):
    from app.core.request_rules import direct_notice_kind

    fields = {"risk_level": "normal", "topic_key": topic, "out_of_scope_kind": "others_privacy"}
    assert direct_notice_kind("inquiry", body, fields) == expected
