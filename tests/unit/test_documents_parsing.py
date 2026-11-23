"""T20 원 자료 읽기·조각 나누기 시험 (T11 가상 원 자료 30개 기준)."""

from datetime import date
from pathlib import Path

import pytest

from app.modules.documents import DocumentFormatError, parse_document
from app.modules.documents.parsing import NO_HEADING_LOCATION

FIXTURES = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "kg-demo-01"
DOC_FILES = sorted((f for d in ("notice", "schedule", "menu", "policy", "consult_timetable") for f in FIXTURES.glob(f"{d}/*.md")))


def load(doc_id: str):
    path = next(p for p in DOC_FILES if p.stem == doc_id)
    return parse_document(path.read_text(encoding="utf-8"))


def test_all_fixture_documents_parse():
    assert len(DOC_FILES) == 30  # T11 README '적재 대상 30개'
    for path in DOC_FILES:
        doc = parse_document(path.read_text(encoding="utf-8"))
        assert doc.meta.id == path.stem
        assert doc.meta.source == "virtual" and doc.meta.is_virtual
        assert doc.chunks, f"{path.stem}: 조각이 없음"
        assert len(doc.content_sha256) == 64


def test_meta_matches_documents_columns():
    doc = load("NT-2026-26")
    assert doc.meta.title == "11월 현장체험학습 안내 (만 5세반)"
    assert doc.meta.doc_type == "notice"
    assert doc.meta.kindergarten_id == "KG-DEMO-01"
    assert doc.meta.classroom_keys == ("C5",)
    assert doc.meta.effective_from == date(2026, 11, 10)
    assert doc.meta.visibility == "all"
    assert not doc.meta.is_org_wide


def test_org_wide_document_has_no_classroom_keys():
    doc = load("NT-2026-25")
    assert doc.meta.classroom_keys == ()
    assert doc.meta.is_org_wide


def test_multi_classroom_document():
    assert load("NT-2026-30").meta.classroom_keys == ("C4", "C5")


def test_headings_become_locations():
    doc = load("NT-2026-26")
    locations = [c.location for c in doc.chunks]
    assert "2쪽 준비물" in locations  # 30문항 YC-M08 근거 위치
    chunk = next(c for c in doc.chunks if c.location == "2쪽 준비물")
    assert "도시락" in chunk.content


def test_chunk_index_is_sequential():
    for path in DOC_FILES:
        doc = parse_document(path.read_text(encoding="utf-8"))
        assert [c.index for c in doc.chunks] == list(range(len(doc.chunks)))


def test_preamble_is_not_evidence():
    for path in DOC_FILES:
        doc = parse_document(path.read_text(encoding="utf-8"))
        for chunk in doc.chunks:
            assert "가상 자료입니다" not in chunk.content
            assert "원훈" not in chunk.content
            assert "- 시행일:" not in chunk.content


def test_table_only_document_is_one_body_chunk():
    doc = load("SC-2026-2H")
    assert [c.location for c in doc.chunks] == [NO_HEADING_LOCATION]
    assert "겨울방학" in doc.chunks[0].content


def test_quote_from_fixture_is_inside_a_chunk():
    doc = load("NT-2026-25")
    chunk = next(c for c in doc.chunks if c.location == "1쪽 겨울방학 기간")
    assert "2026년 12월 24일(목) ~ 2027년 1월 3일(일)" in chunk.content


@pytest.mark.parametrize(
    "text, message",
    [
        ("# 제목\n본문", "머리말"),
        ("---\ntitle: x\n", "닫히지"),
        ("---\ntitle: x\ndoc_type: notice\n---\n", "필수 값"),
        (
            "---\ntitle: x\ndoc_type: memo\nkindergarten_id: K\neffective_from: 2026-11-01\nvisibility: all\nsource: virtual\n---\n",
            "doc_type",
        ),
        (
            "---\ntitle: x\ndoc_type: notice\nkindergarten_id: K\neffective_from: 2026/11/01\nvisibility: all\nsource: virtual\n---\n",
            "effective_from",
        ),
    ],
)
def test_bad_front_matter_is_rejected(text, message):
    with pytest.raises(DocumentFormatError, match=message):
        parse_document(text)
