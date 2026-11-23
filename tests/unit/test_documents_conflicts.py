"""T20 문서 충돌 찾기 시험. T11 자료의 의도된 충돌은 겨울방학 하나뿐이다(T11 README '의도한 시험 장치')."""

from pathlib import Path

from app.modules.documents import find_conflicts, parse_document
from app.modules.documents.conflicts import normalize_label

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "kg-demo-01"
DOCS = [parse_document(p.read_text(encoding="utf-8")) for p in sorted((f for d in ("notice", "schedule", "menu", "policy", "consult_timetable") for f in FIXTURES.glob(f"{d}/*.md")))]


def by_id(doc_id):
    return next(d for d in DOCS if d.meta.id == doc_id)


def make(doc_id, body, *, classroom_keys="[]", effective_from="2026-11-16", title="안내"):
    return parse_document(
        f"---\nid: {doc_id}\ntitle: \"{title}\"\ndoc_type: notice\nkindergarten_id: KG-DEMO-01\n"
        f"classroom_keys: {classroom_keys}\neffective_from: {effective_from}\nvisibility: all\n"
        f"source: virtual\nis_virtual: true\n---\n\n## 1쪽 안내\n{body}\n"
    )


def test_fixture_corpus_has_exactly_the_intended_conflict():
    found = []
    for i, doc in enumerate(DOCS):  # 문서를 하나씩 올린다고 보고 앞서 올린 문서와 비교
        found += [(doc.meta.id, c) for c in find_conflicts(doc, DOCS[:i])]
    assert len(found) == 1
    _, c = found[0]
    assert c.label == "겨울방학"
    assert {c.value.split("~")[0], c.other_value.split("~")[0]} == {"2026-12-24", "2026-12-26"}
    assert {c.other_document_id} <= {"NT-2026-25", "SC-2026-2H"}


def test_conflict_is_found_in_either_upload_order():
    notice, schedule = by_id("NT-2026-25"), by_id("SC-2026-2H")
    a = find_conflicts(notice, [schedule])
    b = find_conflicts(schedule, [notice])
    assert [c.label for c in a] == ["겨울방학"]
    assert [c.label for c in b] == ["겨울방학"]
    assert a[0].location == "1쪽 겨울방학 기간"
    assert a[0].other_location == "본문"


def test_same_event_same_date_in_notice_and_schedule_is_not_conflict():
    # 재롱잔치: 초대장 '일시' 12/18, 12월 일정표 12-18 → 같음
    assert find_conflicts(by_id("NT-2026-28"), [by_id("SC-2026-12"), by_id("SC-2026-2H")]) == []


def test_different_event_with_similar_name_is_not_compared():
    assert normalize_label("2학기 개학") != normalize_label("개학")
    assert normalize_label("재롱잔치 총연습") != normalize_label("**재롱잔치** (햇살 구민회관 소강당, 10:30)")
    assert normalize_label("12월 재롱잔치 초대장") == "재롱잔치"
    assert normalize_label("만 3세반 숲 체험 안내") == "숲 체험"


def test_changed_date_is_flagged():
    new = make("NEW-1", "- 재롱잔치: 2026년 12월 19일(토) 오전 10:30")
    conflicts = find_conflicts(new, [by_id("SC-2026-12")])
    assert len(conflicts) == 1
    assert conflicts[0].value == "2026-12-19"
    assert conflicts[0].other_value == "2026-12-18"
    assert conflicts[0].to_dict()["other_document_title"] == "12월 월간 일정"


def test_changed_number_is_flagged():
    old = make("OLD", "- 등원 기준 체온: 37.5℃ 이상이면 등원하지 않음")
    new = make("NEW", "- 등원 기준 체온: 38℃ 이상이면 등원하지 않음")
    conflicts = find_conflicts(new, [old])
    assert [(c.kind, c.value, c.other_value) for c in conflicts] == [("number", "38℃", "37.5℃")]


def test_time_is_not_read_as_number():
    old = make("OLD", "- 출발: 09:30 원에서 출발")
    new = make("NEW", "- 출발: 10:30 원에서 출발")
    assert find_conflicts(new, [old]) == []


def test_documents_for_other_classrooms_are_not_compared():
    c3 = make("C3-DOC", "- 숲 체험: 2026년 11월 24일(화)", classroom_keys="[C3]")
    c5 = make("C5-DOC", "- 숲 체험: 2026년 11월 25일(수)", classroom_keys="[C5]")
    assert find_conflicts(c5, [c3]) == []


def test_org_wide_document_is_compared_with_class_document():
    whole = make("ALL-DOC", "- 숲 체험: 2026년 11월 24일(화)")
    c3 = make("C3-DOC", "- 숲 체험: 2026년 11월 25일(수)", classroom_keys="[C3]")
    assert len(find_conflicts(c3, [whole])) == 1


def test_year_is_inferred_for_next_year_months():
    # 11월 시행 문서의 '1월 4일'은 다음 해
    new = make("NEW", "- 개학: 1월 4일(월)", effective_from="2026-11-02")
    old = make("OLD", "- 개학: 2027년 1월 4일(월)")
    assert find_conflicts(new, [old]) == []


def test_range_end_without_month():
    new = make("NEW", "- 학부모 상담 주간: 2026년 11월 16일(월) ~ 21일(토)")
    conflicts = find_conflicts(new, [by_id("SC-2026-11")])
    assert [(c.value, c.other_value) for c in conflicts] == [("2026-11-16~2026-11-21", "2026-11-16~2026-11-20")]


def test_same_document_is_skipped():
    doc = by_id("NT-2026-25")
    assert find_conflicts(doc, [doc]) == []
