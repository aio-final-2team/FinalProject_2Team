"""이름과 낱말을 구분하고 조사·호칭·문장부호를 보존해요."""

import pytest

from app.core.memory_rules import mask_child_names


@pytest.mark.parametrize("suffix", [
    "", "이", "가", "은", "는", "을", "를", "의", "에게", "한테", "랑", "이랑", "와", "과", "도", "만",
    "아", "야", "님", "이네", "이가", "이는", "이를", "이도", "이의", "이에게", "이한테", "이와", "이님",
])
def test_name_before_particle_or_title_keeps_suffix(suffix):
    assert mask_child_names(f"하늘{suffix} 확인해 주세요", ["하늘"]) == f"○○{suffix} 확인해 주세요"


@pytest.mark.parametrize("content", [
    "하늘색", "무엇이든", "마루에서", "올라온", "다가온", "김하늘", "바다반", "하늘이가족", "하늘a", "하늘7", "하늘_",
])
def test_name_inside_word_is_preserved(content):
    assert mask_child_names(content, ["하늘", "이든", "마루", "라온", "가온", "바다"]) == content


def test_name_boundaries_overlap_and_empty_candidates():
    assert mask_child_names("(하늘), ‘마루’!\n하늘이랑", ["하늘", "하늘이", "마루", "하늘", "", None]) == (
        "(○○), ‘○○’!\n○○랑"
    )
    assert mask_child_names("[TEST] 하늘", []) == "[TEST] 하늘"


CARE = "평소 낮잠 전에 책을 읽어 줘요."
PREF = "평소 상담은 오후 4시 이후를 선호해요."


@pytest.mark.parametrize("body", ["오늘만 낮잠 전에 책을 읽어 주세요.", "친구는 평소 견과류 알레르기가 있어요.",
                                  "상담 연락은 문자로 받고 싶어요.", "견과류 알레르기가 있어요.",
                                  "[TEST] 수족구에 걸렸는데 평소처럼 등원해도 되나요?", "[TEST] 준비물 알려 주세요"])
def test_model_absent_fallback_skips_one_off_other_child_question_and_non_repeat(body):
    """[TEST] 모델 없음 대역: 일회성·다른 아이 낱말, 질문, 반복 낱말이 없는 문장은 후보로 내지 않아요."""
    from app.core.memory_rules import fallback_parent_candidates
    assert fallback_parent_candidates(body) == []


def test_model_absent_fallback_picks_care_and_repeat_preference_with_times():
    """[TEST] 모델 없음 대역: 돌봄 낱말 문장과 반복 선호 문장을 원문 그대로, 시각은 구조값으로 내요."""
    from app.core.memory_rules import fallback_parent_candidates, parent_candidates
    found = fallback_parent_candidates(f"{CARE} {PREF}")
    assert found == [{"kind": "care_note", "content": CARE, "structured": {}},
                     {"kind": "preference", "content": PREF, "structured": {"after": "16:00"}}]
    assert list(parent_candidates(found, f"{CARE} {PREF}", [])) == found


def test_parent_candidates_follow_ai_kind_but_keep_lines():
    """[TEST] AI가 고른 종류는 따르고, 원문·진단·민감정보·돌봄 가장 선호는 코드가 막아요."""
    from app.core.memory_rules import parent_candidates
    body = "상담 연락은 문자로 받고 싶어요."
    assert [c["content"] for c in parent_candidates([{"kind": "preference", "content": body}], body, [])] == [body]
    assert list(parent_candidates([{"kind": "preference", "content": "평소 낮잠은 길게 자요."}],
                                  "평소 낮잠은 길게 자요.", [])) == []
    assert list(parent_candidates([{"kind": "care_note", "content": "낮잠이 어려워요."}],
                                  "ADHD 진단으로 낮잠이 어려워요.", [])) == []
    assert list(parent_candidates([{"kind": "care_note", "content": "낮잠을 길게 재워 주세요."}],
                                  "낮잠을 짧게 재워 주세요.", [])) == []


def test_checked_rule_keeps_ai_text_and_time_contract():
    """[TEST] 기억 AI 규칙 제안은 계약 칸만 받고 이유 코드를 코드가 붙여요."""
    from app.core.memory_rules import checked_rule
    reply = {"rule": {"rule_text": "[TEST] 화요일 오전에는 상담을 잡지 않아요",
                      "rule_json": {"weekdays": [1], "after": "12:00", "note": "버림"}}}
    assert checked_rule(reply, "slot_unavailable", ["하늘"]) == (
        "[TEST] 화요일 오전에는 상담을 잡지 않아요", {"reason_code": "slot_unavailable", "weekdays": [1], "after": "12:00"})
    assert checked_rule({"rule": None}, "other", []) is None


@pytest.mark.parametrize("rule", [
    {"rule_text": "[TEST] 하늘이 상담은 오후로", "rule_json": {}},
    {"rule_text": "[TEST] 010-1234-5678로 연락", "rule_json": {}},
    {"rule_text": "[TEST] 천식이 있는 아이는 따로", "rule_json": {}},
    {"rule_text": "[TEST] " + "가" * 80, "rule_json": {}},
    {"rule_text": "[TEST] 오후만", "rule_json": {"after": "16:00", "before": "15:00"}},
    {"rule_text": "[TEST] 요일", "rule_json": {"weekdays": [7]}},
    {"rule_text": "[TEST] 모양", "rule_json": []},
])
def test_checked_rule_rejects_names_sensitive_private_long_and_bad_json(rule):
    from app.core.errors import ApiError
    from app.core.memory_rules import checked_rule
    with pytest.raises((ValueError, ApiError)):
        checked_rule({"rule": rule}, "slot_unavailable", ["하늘"])
