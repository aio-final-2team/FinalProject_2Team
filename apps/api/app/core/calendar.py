"""[제안] DB 의존성 없이 날짜 추출·반 범위를 두 백엔드에 같이 적용해요."""

import re
from datetime import date

from agents.guardrails.injection import suspicious_chunk
from app.core.schedule import KST
from app.modules.documents.conflicts import extract_facts
from app.modules.documents.parsing import Chunk, DocumentMeta, ParsedDocument


def items(user, documents, start, end):
    from app import backend

    classes = (backend.users.classroom_ids_of(user.id) if user.role == "teacher" else
               [c.classroom_id for c in backend.users.children_of(user.id)] if user.role == "parent" else [])
    result = []
    for doc in documents:
        if doc["org_id"] != user.org_id or doc["status"] != "active" or doc["ingest_status"] != "succeeded" \
                or doc["doc_type"] not in ("schedule", "notice"):
            continue
        if (user.role == "parent" and doc["visibility"] == "staff") or (
                user.role != "director" and doc["classroom_ids"] and not set(classes).intersection(doc["classroom_ids"])):
            continue
        meta = {k: doc[k] for k in ("title", "doc_type", "visibility", "source", "is_virtual")}
        meta["effective_from"] = doc["effective_from"] or doc["created_at"].astimezone(KST).date()
        parsed = ParsedDocument(DocumentMeta(id=str(doc["id"]), kindergarten_id=str(doc["org_id"]),
                                classroom_keys=(), **meta), "", doc["content_sha256"], tuple(
            Chunk(c["chunk_index"], c["location"] or "", c["content"]) for c in doc["chunks"]
            if not suspicious_chunk(c["content"])))  # 검색처럼 의심 조각은 일정에도 안 보임(T55 G-6)
        for fact in extract_facts(parsed):
            if fact.kind != "date":
                continue
            first, span, last = fact.value.partition("~")
            day, until = date.fromisoformat(first), date.fromisoformat(last) if span else None
            if day <= end and (until or day) >= start:
                result.append({"date": day, "end_date": until, "title": fact.label, "document_id": doc["id"],
                               "document_title": fact.document_title, "location": fact.location})
    result.sort(key=lambda r: (r["date"], r["title"], r["document_title"], r["location"]))
    return {"items": merged(result)}


def merged(rows):
    """같은 날·같은 기간·같은 이름(띄어쓰기 무시)은 한 줄로 합치고, 이름이 같은데 시작일이 다르면 표시해요.

    기존 칸은 정렬 순서상 첫 자료로 채우고 모든 자료는 sources에 담아요. 시작일이 다르면 어느 쪽이 맞는지
    알 수 없어서 둘 다 남기고 conflict·conflict_dates로 알려요(기준은 clashing). 비교는 조회 구간 안에 나온 일정끼리만 해요."""
    groups, starts = {}, {}
    for row in rows:
        name = re.sub(r"\s+", "", row["title"])
        item = groups.setdefault((row["date"], row["end_date"], name), row | {"sources": []})
        source = {k: row[k] for k in ("document_id", "document_title", "location")}
        if source not in item["sources"]:
            item["sources"].append(source)
        starts.setdefault(name, {}).setdefault(row["date"], set()).add(row["document_id"])
    for (day, _, name), item in groups.items():
        days = clashing(starts[name], day)
        item["conflict"], item["conflict_dates"] = bool(days), days
    return list(groups.values())


CLASH_DAYS = 14  # 같은 행사를 이만큼 안의 다른 날로 적은 자료끼리만 충돌로 봐요


def clashing(by_day, day):
    """다른 자료가 같은 행사를 2주 안의 다른 날로 적었으면 그 날짜들을 돌려줘요.
    한 자료 안의 날짜끼리(매주 숲 체험)나 두 자료가 똑같이 적은 반복 행사는 충돌이 아니에요.
    자료마다 서로 가장 가까운 날짜끼리만 짝지어, 12/03·12/10을 적은 자료와 12/11을 적은 자료는 12/10·12/11만 충돌이에요."""
    dates = {}
    for d, docs in by_day.items():
        for doc in docs:
            dates.setdefault(doc, set()).add(d)

    def nearest(doc, target):
        gap = min(abs((d - target).days) for d in dates[doc])
        return {d for d in dates[doc] if abs((d - target).days) == gap}

    found = {d for d in by_day if d != day and abs((d - day).days) <= CLASH_DAYS
             and any(d in nearest(there, day) and day in nearest(here, d)
                     for here in by_day[day] - by_day[d] for there in by_day[d] - by_day[day])}
    return sorted(found | {day}) if found else []
