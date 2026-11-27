"""모델 없음·실패 대역(classify·scope_kind)과 선(child_harm)이에요. 평소 판단은 감독 AI가 해요(test_request_supervisor.py)."""

import pytest

from app.core.constants import notification_title
from app.core.request_rules import child_harm, classify, direct_notice_kind, scope_kind

RISK_TYPES = ("inquiry", "consultation", "complaint")


@pytest.mark.parametrize("body", [
    # '안전'·'신고'·'개인정보' 낱말 하나로 민원을 긴급으로 올리던 대역 규칙은 없앴어요. 이런 글은 감독 AI가 판단해요.
    "현장체험 안전 수칙 알려 주세요", "결석 신고는 어떻게 해요?", "개인정보 동의서는 어디에 내요?",
    "구청에 신고합니다", "우리 아이 개인정보를 단톡방에 올리셨어요", "버스에서 안전벨트를 안 채워 줬어요",
    "경찰에서 오는 교통안전 교육은 언제예요?",
])
@pytest.mark.parametrize("request_type", RISK_TYPES)
def test_single_words_do_not_raise_risk_in_fallback(request_type, body):
    got = classify(request_type, body)
    assert (got["risk_level"], got["risk_category"], got["urgency"]) == ("normal", None, "normal")


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
    # 본문의 '판단 필요' 글자로 등급을 정하던 규칙은 없앴어요. 판단 필요는 감독 AI만 정해요.
    ("[TEST] 판단 필요 민원이에요", "normal", None),
    ("등원 버스가 늦었어요", "normal", None),
    # 선은 낱말 경계를 봐요: 사람에게 맞은 일·피·멍은 긴급, '맞춰'·주사·멍때림·멍멍이는 아니에요
    ("[TEST] 친구한테 맞아서 울었대요", "urgent", "child_safety"),
    ("[TEST] 코피가 났어요", "urgent", "child_safety"),
    ("[TEST] 엄마한테 맞춰 주세요", "normal", None),
    ("[TEST] 독감 주사 맞고 왔어요", "normal", None),
    ("[TEST] 수업 중에 자꾸 멍때린대요", "normal", None),
    ("[TEST] 멍멍이 인형이 들어 있어요", "normal", None),
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
def test_fallback_scope_kind_leaves_our_child_and_safety_to_people(body, topic, expected):
    assert scope_kind(body, topic) == expected


@pytest.mark.parametrize("risk,expected", [("normal", "others_privacy"), ("uncertain", None), ("urgent", None)])
def test_direct_notice_follows_model_scope_kind_after_risk(risk, expected):
    # 감독 AI가 권한 밖이라고 정하면 낱말('우리 아이')로 뒤집지 않아요. 위험이면 사람이 먼저예요(선).
    fields = {"risk_level": risk, "topic_key": "peer_conflict", "out_of_scope_kind": "others_privacy"}
    assert direct_notice_kind("inquiry", "[TEST] 우리 아이 친구 엄마 번호 알려 주세요", fields) == expected


def test_child_harm_line_is_shared_by_fallback():
    assert child_harm("[TEST] 선생님에게 맞은 것 같아요") and not child_harm("[TEST] 시간을 엄마한테 맞춰 주세요")
