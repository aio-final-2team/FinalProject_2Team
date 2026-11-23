"""원 자료 Markdown을 읽어 문서 정보와 근거 조각으로 나눈다.

입력 형식은 T11 가상 원 자료(`data/fixtures/kg-demo-01`)와 같다.
- 맨 위 머리말(front matter): `documents` 표 열 이름과 같은 키
- 본문 `## 1쪽 겨울방학 기간` 같은 제목 하나가 조각 하나이고, 그 제목이 근거 위치(`document_chunks.location`)
- 제목이 없는 문서(일정표·식단표처럼 표만 있는 문서)는 본문 전체가 조각 하나, 위치는 '본문'
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date

DOC_TYPES = {"notice", "schedule", "menu", "policy", "consult_timetable", "law", "public_data"}
VISIBILITIES = {"staff", "parents", "all"}
SOURCES = {"uploaded", "virtual", "public_api"}
REQUIRED_KEYS = ("title", "doc_type", "kindergarten_id", "effective_from", "visibility", "source")

NO_HEADING_LOCATION = "본문"

# 본문 앞부분 중 근거로 쓰지 않는 줄: 가상 자료 표시, 대상 반·시행일 안내(머리말과 같은 정보)
_PREAMBLE_LINE = re.compile(r"^(> ※|- 대상 반:|- 시행일:)")
# 통신문 머리(원훈·호수) 표
_LETTERHEAD_HEADER = re.compile(r"^\|\s*원훈\s*\|")


class DocumentFormatError(ValueError):
    """머리말이 없거나 값이 허용 범위 밖인 문서."""


@dataclass(frozen=True)
class DocumentMeta:
    id: str | None
    title: str
    doc_type: str
    kindergarten_id: str
    classroom_keys: tuple[str, ...]
    effective_from: date
    visibility: str
    source: str
    is_virtual: bool
    published_at: date | None = None
    classroom: str | None = None

    @property
    def is_org_wide(self) -> bool:
        """대상 반이 비어 있으면 원 전체 자료다(`document_classrooms` 줄 없음)."""
        return not self.classroom_keys


@dataclass(frozen=True)
class Chunk:
    index: int
    location: str
    content: str


@dataclass(frozen=True)
class ParsedDocument:
    meta: DocumentMeta
    body: str
    content_sha256: str
    chunks: tuple[Chunk, ...] = field(default_factory=tuple)


def parse_document(text: str) -> ParsedDocument:
    """Markdown 문서 하나를 읽어 문서 정보·본문·조각을 돌려준다."""
    raw_meta, body = _split_front_matter(text)
    meta = _build_meta(raw_meta)
    return ParsedDocument(
        meta=meta,
        body=body,
        content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        chunks=tuple(split_chunks(body)),
    )


def split_chunks(body: str) -> list[Chunk]:
    """본문을 `## ` 제목 단위로 나눈다. 제목이 없으면 본문 전체가 조각 하나다."""
    lines = _strip_preamble(body.splitlines())
    sections: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    loose: list[str] = []

    for line in lines:
        if line.startswith("## "):
            current = (line[3:].strip(), [line])
            sections.append(current)
        elif current is not None:
            current[1].append(line)
        else:
            loose.append(line)

    chunks: list[Chunk] = []
    loose_text = _clean(loose)
    if loose_text:
        chunks.append(Chunk(index=0, location=NO_HEADING_LOCATION, content=loose_text))
    for location, section_lines in sections:
        content = _clean(section_lines)
        if content:
            chunks.append(Chunk(index=len(chunks), location=location, content=content))
    return chunks


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise DocumentFormatError("머리말(---)이 없습니다")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration as exc:
        raise DocumentFormatError("머리말이 닫히지 않았습니다") from exc

    raw: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise DocumentFormatError(f"머리말 줄 형식이 틀렸습니다: {line!r}")
        raw[key.strip()] = value.strip()
    return raw, "\n".join(lines[end + 1 :])


def _build_meta(raw: dict[str, str]) -> DocumentMeta:
    missing = [k for k in REQUIRED_KEYS if not raw.get(k)]
    if missing:
        raise DocumentFormatError(f"머리말에 필수 값이 없습니다: {', '.join(missing)}")

    doc_type = _unquote(raw["doc_type"])
    visibility = _unquote(raw["visibility"])
    source = _unquote(raw["source"])
    if doc_type not in DOC_TYPES:
        raise DocumentFormatError(f"허용되지 않은 doc_type: {doc_type}")
    if visibility not in VISIBILITIES:
        raise DocumentFormatError(f"허용되지 않은 visibility: {visibility}")
    if source not in SOURCES:
        raise DocumentFormatError(f"허용되지 않은 source: {source}")

    return DocumentMeta(
        id=_unquote(raw["id"]) if raw.get("id") else None,
        title=_unquote(raw["title"]),
        doc_type=doc_type,
        kindergarten_id=_unquote(raw["kindergarten_id"]),
        classroom_keys=_parse_list(raw.get("classroom_keys", "[]")),
        effective_from=_parse_date(raw["effective_from"], "effective_from"),
        visibility=visibility,
        source=source,
        is_virtual=_unquote(raw.get("is_virtual", "true")).lower() == "true",
        published_at=_parse_date(raw["published_at"], "published_at") if raw.get("published_at") else None,
        classroom=_unquote(raw["classroom"]) if raw.get("classroom") else None,
    )


def _strip_preamble(lines: list[str]) -> list[str]:
    kept: list[str] = []
    in_letterhead = False
    for line in lines:
        if line.startswith("# "):
            continue  # 문서 제목은 머리말 title과 같다
        if _PREAMBLE_LINE.match(line):
            continue
        if _LETTERHEAD_HEADER.match(line):
            in_letterhead = True
            continue
        if in_letterhead:
            if line.startswith("|"):
                continue
            in_letterhead = False
        kept.append(line)
    return kept


def _clean(lines: list[str]) -> str:
    kept = [line.rstrip() for line in lines if line.strip() != "---"]
    return "\n".join(kept).strip()


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def _parse_list(value: str) -> tuple[str, ...]:
    value = value.strip()
    if not (value.startswith("[") and value.endswith("]")):
        raise DocumentFormatError(f"목록 형식이 틀렸습니다: {value!r}")
    return tuple(_unquote(item) for item in value[1:-1].split(",") if item.strip())


def _parse_date(value: str, key: str) -> date:
    try:
        return date.fromisoformat(_unquote(value))
    except ValueError as exc:
        raise DocumentFormatError(f"{key} 날짜 형식이 틀렸습니다(YYYY-MM-DD): {value!r}") from exc
