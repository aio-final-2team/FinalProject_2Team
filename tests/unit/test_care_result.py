"""돌봄 처리 결과 한 줄과 요청 의도 읽기 규칙."""

from datetime import UTC, datetime

import pytest

from app.core.care import note_result, request_intent, result_line


@pytest.mark.parametrize("req_type,at,expected", [
    ("medication", datetime(2026, 11, 27, 4, 0, tzinfo=UTC), "13시에 약 먹였어요"),
    ("medication", datetime(2026, 11, 27, 4, 5, tzinfo=UTC), "13시 5분에 약 먹였어요"),
    ("pickup", datetime(2026, 11, 27, 7, 30, tzinfo=UTC), "16시 30분에 귀가했어요"),
])
def test_blank_result_uses_kst_time_and_kind(req_type, at, expected):
    for blank in (None, "", "   \n"):
        assert result_line(req_type, blank, at) == expected


def test_teacher_result_is_kept_trimmed():
    at = datetime(2026, 11, 27, 4, 0, tzinfo=UTC)
    assert result_line("medication", "  [TEST] 점심 뒤 시럽 5mL 먹였어요\n", at) == "[TEST] 점심 뒤 시럽 5mL 먹였어요"


def test_note_result_masks_before_model_and_keeps_missing_as_none():
    assert note_result("[TEST] 이모(010-1234-5678)께 인계했어요") == "[TEST] 이모([전화번호])께 인계했어요"
    assert note_result(None) is None


@pytest.mark.parametrize("req_type,stored,expected", [
    ("medication", None, "ask"), ("pickup", "notice", "ask"),
    ("inquiry", "notice", "notice"), ("inquiry", None, None), ("complaint", "ask", "ask"),
])
def test_care_requests_are_always_ask_and_others_keep_ai_value(req_type, stored, expected):
    assert request_intent(req_type, stored) == expected
