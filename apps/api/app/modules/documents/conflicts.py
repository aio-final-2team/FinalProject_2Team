"""문서끼리 같은 항목의 날짜·숫자가 다른지 찾는다(FR-13, NFR-07).

규칙 기반이라 모델을 부르지 않는다. 찾는 사실은 두 가지다.
- 날짜: `- 겨울방학: 2026년 12월 24일 ~ …` 같은 목록 줄, `| 12-18(금) | 재롱잔치 | 전체 |` 같은 표 줄
- 숫자: `- 이름: 37.5℃` 처럼 목록 줄에 단위(℃·원·분·명)가 붙은 값

항목 이름(label)을 정규화해 **이름이 같고 대상 반이 겹치는데 값이 다르면** 충돌이다.
충돌이 있으면 새 문서는 `conflict_pending`이 되고 사람이 확인한다(T04 합의 7, 계약표 1.1 규칙 12).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from .parsing import ParsedDocument

# 날짜를 찾지 않는 문서 종류: 식단표 표의 둘째 칸은 행사 이름이 아니고, 상담 시간표는 빈 시간 목록이다
_SKIP_DATE_DOC_TYPES = {"menu", "consult_timetable"}
# 항목 이름으로 쓰기엔 너무 일반적인 목록 머리. 이때는 문서 제목을 항목 이름으로 쓴다
_GENERIC_LABELS = {"일시", "날짜", "기간", "일정", "때"}
# 문서 정보 줄이라 사실로 보지 않는 목록 머리
_META_LABELS = {"시행일", "대상 반", "기준일", "담당 교사 ID"}

_BULLET = re.compile(r"^\s*[-*]\s+(?P<label>[^:：]{1,30})[:：]\s*(?P<rest>.+)$")
_TABLE_ROW = re.compile(r"^\|(?P<cells>.+)\|\s*$")
_FULL_KO = re.compile(r"(?P<y>\d{4})년\s*(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일")
_MONTH_DAY_KO = re.compile(r"(?<![\d년])(?P<m>\d{1,2})월\s*(?P<d>\d{1,2})일")
_DAY_ONLY_KO = re.compile(r"(?<![\d월])(?P<d>\d{1,2})일")
_ISO = re.compile(r"(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})")
_MM_DD = re.compile(r"(?<![\d-])(?P<m>\d{1,2})-(?P<d>\d{2})(?![\d-])")
# 숫자 바로 뒤에 단위가 붙은 값만(시각 '09:30 원에서'의 '30 원'은 아님)
_NUMBER_UNIT = re.compile(r"(?<![\d:.,])(?P<value>\d+(?:[.,]\d+)*)(?P<unit>℃|원|분|명)")
_PAREN = re.compile(r"\([^)]*\)")


@dataclass(frozen=True)
class Fact:
    document_id: str | None
    document_title: str
    location: str
    label: str
    kind: str  # "date" | "number"
    value: str  # 비교용 정규화 값(날짜는 ISO, 기간은 "시작~끝", 숫자는 "값+단위")
    text: str  # 원문 줄


@dataclass(frozen=True)
class Conflict:
    label: str
    kind: str
    value: str
    location: str
    other_document_id: str | None
    other_document_title: str
    other_location: str
    other_value: str

    def to_dict(self) -> dict[str, str | None]:
        """API `document.conflicts[]` 한 항목(모양은 T13과 맞출 제안)."""
        return {
            "label": self.label,
            "kind": self.kind,
            "value": self.value,
            "location": self.location,
            "other_document_id": self.other_document_id,
            "other_document_title": self.other_document_title,
            "other_location": self.other_location,
            "other_value": self.other_value,
        }


def find_conflicts(new: ParsedDocument, others: list[ParsedDocument]) -> list[Conflict]:
    """새 문서와 이미 있는(사용 중인) 문서들을 비교해 충돌 목록을 돌려준다."""
    new_facts = extract_facts(new)
    conflicts: list[Conflict] = []
    seen: set[tuple[str, str, str | None, str]] = set()
    for other in others:
        if other.meta.id is not None and other.meta.id == new.meta.id:
            continue
        if not _scopes_overlap(new, other):
            continue
        other_facts = extract_facts(other)
        for fact in new_facts:
            same = [o for o in other_facts if o.kind == fact.kind and o.label == fact.label]
            # 다른 문서에 같은 이름의 값이 하나라도 같으면 충돌로 보지 않는다(같은 행사가 여러 번 적힌 경우)
            if not same or any(_same_value(fact, o) for o in same):
                continue
            for o in same:
                key = (fact.label, fact.value, o.document_id, o.value)
                if key in seen:
                    continue
                seen.add(key)
                conflicts.append(
                    Conflict(
                        label=fact.label,
                        kind=fact.kind,
                        value=fact.value,
                        location=fact.location,
                        other_document_id=o.document_id,
                        other_document_title=o.document_title,
                        other_location=o.location,
                        other_value=o.value,
                    )
                )
    return conflicts


def extract_facts(doc: ParsedDocument) -> list[Fact]:
    facts: list[Fact] = []
    base = doc.meta.effective_from
    for chunk in doc.chunks:
        for line in chunk.content.splitlines():
            bullet = _BULLET.match(line)
            if bullet:
                raw_label = bullet.group("label").strip()
                if raw_label in _META_LABELS:
                    continue
                label = doc.meta.title if raw_label in _GENERIC_LABELS else raw_label
                rest = bullet.group("rest")
                if doc.meta.doc_type not in _SKIP_DATE_DOC_TYPES:
                    span = _date_span(rest, base)
                    if span:
                        facts.append(_fact(doc, chunk.location, label, "date", span, line))
                number = _NUMBER_UNIT.search(rest)
                if number and not _date_span(rest, base):
                    value = number.group("value").replace(",", "") + number.group("unit")
                    facts.append(_fact(doc, chunk.location, label, "number", value, line))
                continue

            row = _TABLE_ROW.match(line)
            if row and doc.meta.doc_type not in _SKIP_DATE_DOC_TYPES:
                cells = [c.strip() for c in row.group("cells").split("|")]
                if len(cells) >= 2 and not set(cells[0]) <= set("-: "):
                    span = _date_span(cells[0], base)
                    if span:
                        facts.append(_fact(doc, chunk.location, cells[1], "date", span, line))
    return facts


def normalize_label(label: str) -> str:
    """'**12월 재롱잔치 초대장**' → '재롱잔치'. 같은 행사를 같은 이름으로 맞춘다.

    '2학기 개학'처럼 다른 행사를 가리키는 말은 지우지 않는다('개학'과 다름)."""
    s = label.replace("*", "")
    s = _PAREN.sub("", s)
    s = re.sub(r"^\s*\d{1,2}월\s*", "", s)
    s = re.sub(r"^\s*만\s*\d세반?\s*", "", s)
    s = re.sub(r"\s*(안내문|안내|초대장)\s*$", "", s)
    return re.sub(r"\s+", " ", s).strip()


def _fact(doc: ParsedDocument, location: str, label: str, kind: str, value: str, text: str) -> Fact:
    return Fact(
        document_id=doc.meta.id,
        document_title=doc.meta.title,
        location=location,
        label=normalize_label(label),
        kind=kind,
        value=value,
        text=text.strip(),
    )


def _date_span(text: str, base: date) -> str | None:
    """글에서 첫 날짜(와 '~' 뒤 끝 날짜)를 찾아 'YYYY-MM-DD' 또는 '시작~끝'으로 돌려준다."""
    start_text, tilde, end_text = text.partition("~")
    start = _first_date(start_text, base, None)
    if start is None:
        return None
    if tilde:
        end = _first_date(end_text, base, start)
        if end is not None:
            return f"{start.isoformat()}~{end.isoformat()}"
    return start.isoformat()


def _first_date(text: str, base: date, start: date | None) -> date | None:
    candidates: list[tuple[int, date]] = []
    for m in _FULL_KO.finditer(text):
        candidates.append((m.start(), _safe_date(int(m["y"]), int(m["m"]), int(m["d"]))))
    for m in _ISO.finditer(text):
        candidates.append((m.start(), _safe_date(int(m["y"]), int(m["m"]), int(m["d"]))))
    for m in _MONTH_DAY_KO.finditer(text):
        candidates.append((m.start(), _infer_year(int(m["m"]), int(m["d"]), base)))
    for m in _MM_DD.finditer(text):
        if not _inside_iso(text, m.start()):
            candidates.append((m.start(), _infer_year(int(m["m"]), int(m["d"]), base)))
    if start is not None:  # '11월 16일 ~ 20일'의 끝 날짜
        for m in _DAY_ONLY_KO.finditer(text):
            candidates.append((m.start(), _safe_date(start.year, start.month, int(m["d"]))))
    found = [(pos, d) for pos, d in candidates if d is not None]
    return min(found)[1] if found else None


def _inside_iso(text: str, pos: int) -> bool:
    return any(m.start() <= pos < m.end() for m in _ISO.finditer(text))


def _infer_year(month: int, day: int, base: date) -> date | None:
    """연도가 없는 날짜는 시행일 기준. 시행일보다 앞선 달이면 다음 해로 본다(11월 문서의 '1월')."""
    year = base.year + 1 if month < base.month else base.year
    return _safe_date(year, month, day)


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _same_value(a: Fact, b: Fact) -> bool:
    if a.value == b.value:
        return True
    if a.kind == "date":
        # 한쪽만 기간이면 시작일만 비교한다('12-18' vs '12-18~12-18 10:30')
        return a.value.split("~")[0] == b.value.split("~")[0] and ("~" not in a.value or "~" not in b.value)
    return False


def _scopes_overlap(a: ParsedDocument, b: ParsedDocument) -> bool:
    if a.meta.kindergarten_id != b.meta.kindergarten_id:
        return False
    if a.meta.is_org_wide or b.meta.is_org_wide:
        return True
    return bool(set(a.meta.classroom_keys) & set(b.meta.classroom_keys))
