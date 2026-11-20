"""T32 영민 그래프 또는 대역을 실행한다. T29에 Celery 워커로 이동.

queued를 한 실행만 가져간다. writer는 트랜잭션 밖에서 호출하고 아이별 결과는 한 번에 저장한다.
입력 행의 xmin으로 이전 실행의 늦은 저장을 막고, 0003의 아이별 이력을 함께 남긴다.
"""

import json
import logging
from concurrent.futures import Future
from datetime import datetime, time, timedelta
from importlib import import_module
from threading import Thread
from uuid import UUID, uuid4

from sqlalchemy import text

from app.api.schemas.actions import NoteContent
from app.api.schemas.views import OpenCheck
from app.core.config import settings
from app.core.db import transaction
from app.core.schedule import KST
from app.modules.daily_notes.stub_writer import failed_child
from app.modules.daily_notes.events import edited_child_ids, record

log = logging.getLogger(__name__)


def _payload(connection, entry):
    values = {"org": entry["org_id"], "class": entry["classroom_id"], "date": entry["note_date"]}
    classroom = connection.execute(text("SELECT id, name FROM classrooms WHERE id=:class AND org_id=:org"),
                                   values).mappings().one()
    children = connection.execute(text("""
        SELECT id, display_name FROM children WHERE org_id=:org AND classroom_id=:class
        ORDER BY created_at, id
    """), values).mappings().all()
    start = datetime.combine(entry["note_date"], time.min, KST)
    requests = connection.execute(text("""
        SELECT r.id AS request_id, r.child_id, r.type, r.body AS text FROM requests r
        WHERE r.org_id=:org AND r.classroom_id=:class AND r.type IN ('medication','pickup','inquiry')
          AND r.created_at>=:start AND r.created_at<:end
          AND EXISTS (SELECT 1 FROM child_guardians g
                      WHERE (g.child_id,g.org_id,g.user_id)=(r.child_id,r.org_id,r.requester_id))
        ORDER BY r.created_at, r.id
    """), {**values, "start": start, "end": start + timedelta(days=1)}).mappings().all()
    menu = connection.execute(text("""
        SELECT d.id AS document_id, d.title,
               string_agg(c.content, E'\n' ORDER BY c.chunk_index) AS text
        FROM documents d JOIN document_chunks c ON (c.document_id,c.org_id)=(d.id,d.org_id)
        WHERE d.org_id=:org AND d.doc_type='menu' AND d.status='active' AND d.ingest_status='succeeded'
          AND d.visibility IN ('parents','all')
          AND (d.effective_from IS NULL OR d.effective_from<=:date)
          AND (d.effective_to IS NULL OR d.effective_to>=:date)
          AND (NOT EXISTS (SELECT 1 FROM document_classrooms dc WHERE dc.document_id=d.id AND dc.org_id=d.org_id)
               OR EXISTS (SELECT 1 FROM document_classrooms dc
                          WHERE dc.document_id=d.id AND dc.org_id=d.org_id AND dc.classroom_id=:class))
        GROUP BY d.id ORDER BY d.effective_from DESC NULLS LAST, d.created_at DESC, d.id LIMIT 1
    """), values).mappings().one_or_none()
    memos = {m["child_id"]: m["memo"] for m in entry["child_memos"]}
    payload = {"input_id": entry["id"], "note_date": entry["note_date"], "classroom": dict(classroom),
            "activities": entry["activities"], "supplies": entry["supplies"],
            "children": [{"child_id": c["id"], "display_name": c["display_name"],
                          "memo": memos.get(str(c["id"]), ""),
                          "requests": [{k: r[k] for k in ("request_id", "type", "text")}
                                       for r in requests if r["child_id"] == c["id"]]} for c in children],
            "menu": dict(menu) if menu is not None else None}
    return json.loads(json.dumps(payload, default=str))


def _validated(result, payload):
    if not isinstance(result, list):
        raise ValueError("writer 결과는 목록이어야 한다")
    by_child = {}
    expected = {child["child_id"] for child in payload["children"]}
    for row in result:
        child_id = str(UUID(str(row["child_id"])))
        if child_id not in expected:
            raise ValueError("입력에 없는 아이")
        by_child.setdefault(child_id, []).append(row)
    rows = []
    for child in payload["children"]:
        try:
            candidates = by_child.get(child["child_id"], [])
            if len(candidates) != 1:
                raise ValueError("아이 결과 누락 또는 중복")
            row = candidates[0]
            content = NoteContent.model_validate(row["content"])
            checks = [OpenCheck.model_validate(c).model_dump(mode="json") for c in row["open_checks"]]
            if len({c["id"] for c in checks}) != len(checks):
                raise ValueError("확인 ID 중복")
            request_ids = {str(r["request_id"]) for r in child["requests"]}
            for line in content.items:
                if line.key == "child" and not child["memo"].strip():
                    raise ValueError("메모 없는 아이의 child 줄")
                if line.source.type == "request" and str(line.source.request_id) not in request_ids:
                    raise ValueError("다른 아이의 요청 출처")
                if line.source.type == "document" and (payload["menu"] is None or
                        str(line.source.document_id) != str(payload["menu"]["document_id"])):
                    raise ValueError("입력에 없는 문서 출처")
            if any(c["request_id"] is not None and c["request_id"] not in request_ids for c in checks):
                raise ValueError("다른 아이의 요청 확인")
            rows.append({"child_id": child["child_id"], "content": content.model_dump(mode="json", exclude_none=True),
                         "open_checks": checks})
        except (ValueError, KeyError, TypeError):
            rows.append(failed_child(payload, child))
    return rows


def requeue_daily_note_drafts():
    """단일 API 프로세스의 시작 때만 호출한다. 저장은 한 트랜잭션이라 부분 초안은 없다."""
    with transaction() as connection:
        connection.execute(text("UPDATE daily_note_inputs SET draft_status='queued' WHERE draft_status='running'"))
        return connection.scalars(text("""
            SELECT id FROM daily_note_inputs WHERE draft_status='queued' ORDER BY created_at, id
        """)).all()


def _write(payload):
    # 시간 초과 뒤 도착한 결과는 버린다. writer에는 DB 저장 책임이 없다.
    future = Future()

    def invoke():
        try:
            path = ("agents.graphs.daily_note:draft_daily_notes" if settings.daily_note_writer == "graph"
                    else settings.daily_note_writer)
            module, name = path.split(":", 1)
            future.set_result(getattr(import_module(module), name)(payload))
        except BaseException as error:
            future.set_exception(error)

    Thread(target=invoke, name="daily-note-writer", daemon=True).start()
    return future.result(timeout=settings.daily_note_writer_timeout)


def run_daily_note_drafts(input_id):
    with transaction() as connection:
        entry = connection.execute(text("""
            UPDATE daily_note_inputs SET draft_status='running' WHERE id=:id AND draft_status='queued'
            RETURNING *, xmin::text AS run_token
        """), {"id": input_id}).mappings().one_or_none()
        if entry is not None:
            metadata = connection.execute(text("""
                UPDATE cards SET draft=draft || jsonb_build_object('draft_started_at', CURRENT_TIMESTAMP)
                WHERE subject_type='daily_note_batch' AND subject_id=:id AND org_id=:org RETURNING draft
            """), {"id": input_id, "org": entry["org_id"]}).scalar_one()
    if entry is None:
        return
    try:
        with transaction() as connection:
            payload = _payload(connection, entry)
            confirmed = set(connection.scalars(text("""
                SELECT child_id::text FROM daily_notes WHERE input_id=:id AND status IN ('ready','sent')
            """), {"id": input_id}))
            protected = confirmed | edited_child_ids(connection, input_id)
            payload["children"] = [c for c in payload["children"] if c["child_id"] not in protected]
        rows = _validated(_write(payload), payload) if payload["children"] else []
        with transaction() as connection:
            current = connection.execute(text("SELECT xmin::text FROM daily_note_inputs WHERE id=:id FOR UPDATE"),
                                         {"id": input_id}).scalar_one()
            if current != entry["run_token"]:
                return
            edited = edited_child_ids(connection, input_id)
            for row in rows:
                previous = connection.execute(text("""
                    SELECT * FROM daily_notes WHERE input_id=:input AND child_id=:child FOR UPDATE
                """), {"input": input_id, "child": row["child_id"]}).mappings().one_or_none()
                if previous is not None and (previous["status"] in ("ready", "sent") or row["child_id"] in edited):
                    continue
                # c1 같은 writer 내부 ID는 저장 전에 바꾼다. 아이별 실패 확인에도 같은 규칙을 쓴다.
                checks = [{**check, "id": str(uuid4()), "request_id": check.get("request_id")}
                          for check in row["open_checks"]]
                saved = connection.execute(text("""
                    INSERT INTO daily_notes (org_id,input_id,child_id,note_date,status,content,open_checks,ai_original)
                    VALUES (:org,:input,:child,:date,:status,CAST(:content AS jsonb),CAST(:checks AS jsonb),CAST(:content AS jsonb))
                    ON CONFLICT (child_id, note_date) DO UPDATE SET
                        content=EXCLUDED.content, ai_original=EXCLUDED.ai_original,
                        open_checks=EXCLUDED.open_checks, status=EXCLUDED.status
                    WHERE daily_notes.input_id=EXCLUDED.input_id AND daily_notes.status IN ('draft','needs_check')
                    RETURNING *
                """), {"org": entry["org_id"], "input": input_id, "child": row["child_id"], "date": entry["note_date"],
                       "status": "needs_check" if row["open_checks"] else "draft",
                       "content": json.dumps(row["content"], default=str),
                       "checks": json.dumps(checks, default=str)}).mappings().one()
                record(connection, saved, "daily_note_drafted",
                       from_status=previous["status"] if previous else None,
                       **({"regenerated_by": metadata["regenerated_by"]} if metadata.get("regenerated_by") else {}))
            connection.execute(text("UPDATE daily_note_inputs SET draft_status='succeeded' WHERE id=:id"), {"id": input_id})
    except Exception as error:
        # 예외 원문에는 입력 메모가 섞일 수 있어 종류만 기록하고 API에는 고정 오류를 준다.
        log.error("알림장 초안 실패 input_id=%s error_type=%s", input_id, type(error).__name__)
        with transaction() as connection:
            connection.execute(text("""
                UPDATE daily_note_inputs SET draft_status='failed' WHERE id=:id AND xmin::text=:token
            """), {"id": input_id, "token": entry["run_token"]})
