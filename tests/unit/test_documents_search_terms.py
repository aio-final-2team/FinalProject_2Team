"""낱말 검색의 낱말 나누기·점수(DB 없이)."""

from app.modules.documents.search import score, terms


def test_terms_strip_particles_and_question_words():
    assert terms("겨울방학은 언제부터인가요?") == ["겨울방학"]
    assert terms("현장체험학습 도시락 챙겨야 하나요") == ["현장체험학습", "도시락", "챙겨야"]
    assert "12월" in terms("12월 24일 방학") and "우리" not in terms("우리 아이 방학")


def test_score_is_share_of_words_with_title_bonus():
    assert score([], "t", "l", "c") == 0.0
    assert score(["겨울방학", "기간"], "안내", "1쪽", "겨울방학 기간은") == 1.0
    assert score(["겨울방학", "도시락"], "안내", "1쪽", "겨울방학") == 0.5
    assert score(["겨울방학"], "겨울방학 안내", "1쪽", "내용") == 1.0
