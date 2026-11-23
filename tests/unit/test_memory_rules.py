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
