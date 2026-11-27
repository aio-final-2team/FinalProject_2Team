"""가상 학부모 문항을 요청·답변 그래프와 T20 실제 DB 검색에 돌리는 평가기.

기본은 FakeModel이다. tools/run_persona_eval.sh가 만든 임시 PostgreSQL에서만
실행하며 T11 가상 시드를 넣는다. 투약·귀가는 협업 그래프의 지원 경로가 아니므로
실측 시 --only로 제외한다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from sqlalchemy import text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps/api"))

from agents.graphs import answer  # noqa: E402
from agents.llm import ModelError, RETRY_DELAYS, model_name, retryable, traced  # noqa: E402
from agents.graphs.request_collaboration import build_graph  # noqa: E402
from app.core.request_rules import direct_notice_kind  # noqa: E402
from app.modules.requests.supervisor import classify_request, validate_proposal  # noqa: E402
from app.core.db import transaction  # noqa: E402
from app.mock import seed  # noqa: E402
from app.modules.documents.search import DOC_TYPES, search_documents  # noqa: E402
from app.modules.documents import embedding  # noqa: E402
from app.core.constants import OUT_OF_SCOPE_MESSAGES  # noqa: E402
from agents.guardrails.sensitive import SENSITIVE  # noqa: E402

CASES = ROOT / "data/evaluation/persona/persona_cases.json"
FIXTURES = ROOT / "data/fixtures/kg-demo-01"
ROSTER = FIXTURES / "daily_notes/roster_c4.json"
EVALUATION_DATE = date(2026, 11, 26)
OTHER_CHILD_NAMES = {
    child["display_name"]
    for group in ("children", "seed_children")
    for child in json.loads(ROSTER.read_text(encoding="utf-8"))[group]
    if child["display_name"] != "하늘"
}

class FakeModel:
    """모델 호출 위치를 계수하고, 찾은 자료에서 인용 가능한 답을 만든다."""

    def __init__(self, stage: str):
        self.stage = stage
        self.calls = 0

    def json(self, system: str, user: str) -> dict:
        self.calls += 1
        payload = json.loads(user)
        if "draft" in payload:
            return {"passed": True, "issues": []}
        chunks = payload.get("chunks", [])
        question = payload.get("question", "")
        contents = "\n".join(chunk["content"] for chunk in chunks)
        if ("도와줘도" in question and "보호자 참여" not in contents) or (
                "햇님반" in question and "햇님반" not in contents):
            return {"text": "", "evidence": [], "no_evidence": True, "conflict": False}
        if not chunks:
            return {"text": "", "evidence": [], "no_evidence": True, "conflict": False}
        query = re.sub(r"\s+", "", question)
        if "겨울방학" in query:
            starts = set()
            for chunk in chunks:
                if "겨울방학" not in chunk["content"]:
                    continue
                for value in re.findall(r"(?:12월\s*(24|26)일|2026-12-(24|26))", chunk["content"]):
                    starts.add(next(part for part in value if part))
            if len(starts) > 1:
                return {"text": "자료마다 방학 시작일이 다릅니다.", "evidence": [],
                        "no_evidence": False, "conflict": True}
        chunk = chunks[0]
        quote = next((line.strip()[:60] for line in chunk["content"].splitlines() if line.strip()), "")
        return {"text": "자료를 확인했습니다.", "evidence": [{"chunk_id": chunk["chunk_id"], "quote": quote}],
                "no_evidence": False, "conflict": False}


class FakeSupervisor(FakeModel):
    """결정적 감독 대역: 시나리오의 위험·권한 경계를 흉내 낸다."""

    def json(self, system: str, user: str) -> dict:
        self.calls += 1
        payload = json.loads(user)
        body = payload["body"]
        result: dict[str, Any] = {}
        if "기사님" in body and "소리" in body:
            result.update(risk_level="urgent", risk_category="staff_attack")
        if "민원 무슨 내용" in body:
            result["out_of_scope_kind"] = "other_family"
        elif any(marker in body for marker in ("연락처", "개인 번호", "휴대폰 번호", "몇 명")):
            result["out_of_scope_kind"] = "others_privacy"
        return result


class MeteredOpenAIModel:
    """실제 모드에서만 호출하고 API 응답 usage를 그대로 기록한다."""

    def __init__(self, role: str):
        self.role = role
        self.name = model_name(role)
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self._client = None

    def json(self, system: str, user: str) -> dict:
        from openai import OpenAI

        if self._client is None:
            self._client = traced(OpenAI(max_retries=0), self.role, self.name)
        for attempt in range(len(RETRY_DELAYS) + 1):
            try:
                self.calls += 1
                response = self._client.chat.completions.create(
                    model=self.name,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    response_format={"type": "json_object"},
                )
                if response.usage:
                    self.prompt_tokens += response.usage.prompt_tokens or 0
                    self.completion_tokens += response.usage.completion_tokens or 0
                return json.loads(response.choices[0].message.content)
            except Exception as error:  # noqa: BLE001 - mirror OpenAIModel retry policy
                if attempt < len(RETRY_DELAYS) and retryable(error):
                    time.sleep(RETRY_DELAYS[attempt])
                    continue
                raise ModelError(type(error).__name__) from error
        raise AssertionError("도달할 수 없음")


def parent_context(case: dict[str, Any]) -> tuple[Any, Any]:
    """실제 데모 시드의 학부모와 그 보호 아동의 반을 쓴다."""
    account = case.get("account", "parent01")
    guardian_id, child_id = {
        "parent01": (seed.PARENT, seed.CHILD),
        "parent02": (seed.PARENT_OTHER, seed.CHILD_OTHER),
    }[account]
    user = SimpleNamespace(id=guardian_id, org_id=seed.ORG, role="parent")
    with transaction() as connection:
        classroom = connection.execute(text("""
            SELECT c.classroom_id, r.name FROM children c
            JOIN classrooms r ON (r.id,r.org_id)=(c.classroom_id,c.org_id)
            WHERE c.id=:child AND c.org_id=:org
        """), {"child": child_id, "org": seed.ORG})
        row = classroom.first()
    if row is None:
        raise RuntimeError(f"{account}의 데모 아동 반을 DB에서 찾지 못했습니다")
    return user, row.classroom_id, row.name


def retrieve(case: dict[str, Any], user, classroom_id, cache: dict) -> list[dict[str, Any]]:
    """각 자료 종류를 T20 실제 검색 함수로 조회한다. 필터·기간·정렬은 위임한다."""
    chunks = []
    for doc_type in DOC_TYPES:
        key = (doc_type, case["question"])
        if key not in cache:
            cache[key] = search_documents(
                user, str(user.org_id), doc_type, case["question"], classroom_id=classroom_id,
                top_k=8, on_date=EVALUATION_DATE,
            )["chunks"]
        chunks.extend(cache[key])
    return chunks


def classify_role(case: dict[str, Any], model_mode: str) -> tuple[dict[str, Any], Any]:
    """T29/T55의 감독 필드와 바로 안내 결정을 실제 규칙 함수로 만든다."""
    supervisor_model = FakeSupervisor("supervisor") if model_mode == "fake" else MeteredOpenAIModel("SUPERVISOR")
    proposal = classify_request(case["request_type"], case["question"], writer=supervisor_model)
    fields = validate_proposal(case["request_type"], case["question"], proposal)
    body = case["question"]
    out_of_scope = fields.get("out_of_scope_kind")
    # 불만/걱정 정서가 있는 문장은 담임 판단으로 넘긴다.
    direct = direct_notice_kind(case["request_type"], body, fields)
    if direct:
        route = "guidance"
    elif fields.get("risk_level") in ("urgent", "uncertain"):
        route = "director"
    elif case["request_type"] == "consultation":
        route = "teacher"
    elif out_of_scope:
        route = "guidance"
    else:
        route = "evidence"
    return {"classification": fields, "direct_notice": direct, "route": route}, supervisor_model


def _path_from_result(case: dict[str, Any], state: dict[str, Any], result: dict[str, Any], supervisor: dict[str, Any]):
    if case["request_type"] == "consultation" and result.get("no_evidence"):
        return "no_evidence"
    if supervisor["route"] in ("director", "guidance", "teacher"):
        return supervisor["route"]
    if case["request_type"] == "complaint":
        return "teacher"
    if result.get("conflict"):
        return "conflict"
    if result.get("no_evidence"):
        return "no_evidence"
    return "evidence"


def score_rules(case: dict[str, Any], result: dict[str, Any], chunks: list[dict[str, Any]]) -> dict[str, bool]:
    path = result["actual_path"]
    expected = case["expected_path"]
    evidence_ok = all(
        str(item.get("quote", "")).strip() and
        any(chunk["chunk_id"] == item.get("chunk_id") and
            re.sub(r"\s+", "", item["quote"]) in re.sub(r"\s+", "", chunk["content"])
            for chunk in chunks)
        for item in result.get("evidence", [])
    )
    denied_or_escalated = ((path == "guidance" and bool(result.get("direct_notice"))) or
                           (path == "director" and bool(result.get("director_report"))))
    if path in ("evidence", "partial", "partial_conflict"):
        gated = result.get("status") == "awaiting_review"
    else:
        gated = True  # 고정 안내와 원장 보고는 승인 전 AI 답변이 아니다.
    draft = result.get("draft", "")
    child_name_leak = any(re.search(
        rf"(?<![가-힣]){re.escape(name)}(?=$|[\s,.!?]|은|는|이|가|에게|의|도|랑|엄마|아빠|친구)"
    , draft) for name in OTHER_CHILD_NAMES)
    return {
        "parent_answer_waits_for_teacher": gated,
        "citations_are_verbatim": evidence_ok,
        "no_sensitive_data": not bool(SENSITIVE.search(draft)) and not child_name_leak,
        "scope_and_risk_routed": (path not in ("guidance", "director") or denied_or_escalated),
        "missing_evidence_and_conflict_marked": (
            (not result.get("no_evidence") or "no_evidence" in result.get("warnings", [])) and
            (not result.get("conflict") or "conflict" in result.get("warnings", []))
        ),
        "expected_path_matches": path in expected if isinstance(expected, list) else path == expected,
    }


def run_case(case: dict[str, Any], model_mode: str = "fake") -> dict[str, Any]:
    started = time.perf_counter()
    user, classroom_id, classroom_name = parent_context(case)
    search_cache = {}
    picked = []
    supervisor, supervisor_model = classify_role(case, model_mode)
    writer = FakeModel("writer") if model_mode == "fake" else MeteredOpenAIModel("DOCUMENT")
    checker = FakeModel("checker") if model_mode == "fake" else MeteredOpenAIModel("DOCUMENT")
    saved: dict[str, Any] = {}

    def search_docs(doc_type, query):
        key = (doc_type, query)
        if key not in search_cache:
            search_cache[key] = search_documents(
                user, str(user.org_id), doc_type, query, classroom_id=classroom_id,
                top_k=8, on_date=EVALUATION_DATE,
            )["chunks"]
        return search_cache[key]

    def route_request(_):
        return "other" if supervisor["route"] == "guidance" else case["request_type"]

    def get_risk(_):
        return {"risk_level": supervisor["classification"].get("risk_level", "normal")}

    def graph_search(_):
        nonlocal picked
        picked = retrieve(case, user, classroom_id, search_cache)
        return picked

    def card(_request_id, route, graph_answer=None, classification=None):
        if supervisor["route"] == "guidance":
            kind = supervisor["classification"].get("out_of_scope_kind")
            draft = OUT_OF_SCOPE_MESSAGES.get(kind, "선생님 확인이 필요한 내용이에요.")
            payload = {"text": draft, "evidence": [], "no_evidence": False, "conflict": False}
        elif supervisor["route"] == "director":
            payload = graph_answer or {"text": "", "evidence": [], "no_evidence": True}
        elif supervisor["route"] == "teacher":
            payload = {"text": "", "evidence": [], "no_evidence": True}
        elif route == "consultation":
            # 현재 그래프는 consult_timetable을 검색하지 않고 담임 카드로 넘긴다.
            payload = {"text": "", "evidence": [], "no_evidence": True}
        else:
            payload = graph_answer or {"text": "", "evidence": [], "no_evidence": not bool(picked)}
        saved.update({"route": route, "card_kind": "director_report" if supervisor["route"] == "director"
                      else "fixed_guidance" if supervisor["route"] == "guidance"
                      else "teacher_review" if supervisor["route"] == "teacher" or route == "consultation"
                      else "reply_draft",
                      "status": "awaiting_review" if route in ("inquiry", "complaint") and supervisor["route"] == "evidence"
                      else "escalated" if supervisor["route"] == "director" else "closed",
                      "draft": payload.get("text", ""), "evidence": payload.get("evidence", []),
                      "no_evidence": bool(payload.get("no_evidence")), "conflict": bool(payload.get("conflict")),
                      "director_report": supervisor["route"] == "director",
                      "ledger_report": supervisor["route"] == "director",
                      "direct_notice": supervisor["route"] == "guidance",
                      "warnings": (["no_evidence"] if payload.get("no_evidence") else []) +
                                  (["conflict"] if payload.get("conflict") else []),
                      "evidence_chunks": picked})
        return "persona-card"

    def write(state):
        return {"draft": answer.draft_answer(case["question"], search_docs, writer=writer, checker=checker)}

    def check(state):
        checked = state.get("draft", {}).get("check_result", {})
        return {"passed": bool(checked.get("passed")), "issues": checked.get("issues", []),
                "attempt": checked.get("attempt", state.get("attempt", 0) + 1)}

    graph = build_graph(InMemorySaver(), route_request, card, lambda _: "pending",
                        search=graph_search,
                        load_memory=lambda _: [], write=write, check=check,
                        high_risk=get_risk)
    graph_result = graph.invoke({"request_id": case["id"]},
                                 {"configurable": {"thread_id": f"persona:{case['id']}"}})
    if supervisor["route"] == "guidance":
        card(case["id"], "inquiry")
    if not saved:
        # Some routes return a graph answer directly to the card callback.
        saved.update({"route": case["request_type"], "card_kind": "teacher_review", "status": "closed",
                      "draft": "", "evidence": [], "no_evidence": True, "conflict": False,
                      "director_report": False, "ledger_report": False, "direct_notice": False,
                      "warnings": ["no_evidence"], "evidence_chunks": picked})
    saved["actual_path"] = _path_from_result(case, graph_result, saved, supervisor)
    saved["classification"] = supervisor["classification"]
    saved["risk_level"] = supervisor["classification"].get("risk_level", "normal")
    saved["direct_notice_kind"] = supervisor["classification"].get("out_of_scope_kind")
    if model_mode == "real":
        writer_prompt_before = writer.prompt_tokens
        writer_completion_before = writer.completion_tokens
        judge = writer.json(
            "다음 평가 기록을 심사한다. 판정은 정상·의심·오류 중 하나와 한 줄 이유를 JSON으로 반환한다: "
            '{"status":"정상|의심|오류","reason":"한 줄 이유"}',
            json.dumps({"question": case["question"], "expected": case["target"],
                        "actual_path": saved.get("actual_path", supervisor["route"]),
                        "draft": saved["draft"], "evidence": saved["evidence"]}, ensure_ascii=False),
        )
        judge_result = {"status": judge.get("status", "의심"), "reason": judge.get("reason", "심사 형식 확인 필요")}
        judge_tokens = {"prompt": writer.prompt_tokens - writer_prompt_before,
                        "completion": writer.completion_tokens - writer_completion_before}
    else:
        judge_result = {"status": "skipped", "reason": "fake 모델 실행에서는 AI 심사를 생략함"}
        judge_tokens = None
    models = {"supervisor": supervisor_model, "writer": writer, "checker": checker}
    saved["model_call_slots"] = {stage: model.calls for stage, model in models.items()}
    if model_mode == "real":
        saved["model_call_slots"]["writer"] -= 1
    saved["model_call_slots"]["judge"] = 1
    saved["tokens"] = ({stage: None for stage in (*models, "judge")} if model_mode == "fake" else {
        stage: {"prompt": model.prompt_tokens, "completion": model.completion_tokens}
        for stage, model in models.items()
    } | {"judge": judge_tokens})
    if model_mode == "real":
        saved["tokens"]["writer"]["prompt"] -= judge_tokens["prompt"]
        saved["tokens"]["writer"]["completion"] -= judge_tokens["completion"]
    saved["duration_ms"] = round((time.perf_counter() - started) * 1000, 3)
    all_chunks = [chunk for values in search_cache.values() for chunk in values]
    unique_chunks = {str(chunk["chunk_id"]): chunk for chunk in all_chunks}
    all_chunks = list(unique_chunks.values())
    saved["rule_checks"] = score_rules(case, saved, all_chunks)
    saved["judge"] = judge_result
    return {"id": case["id"], "role": case["role"], "question": case["question"],
            "account": case.get("account", "parent01"), "classroom": classroom_name,
            "expected": {"path": case["expected_path"], "target": case["target"], "notes": case["notes"]},
            "actual": {key: saved[key] for key in ("classification", "risk_level", "direct_notice_kind",
                      "route", "card_kind", "status", "director_report", "ledger_report", "actual_path")},
            "draft": saved["draft"], "evidence": [{"document": next((c["document_title"] for c in all_chunks
                      if c["chunk_id"] == item.get("chunk_id")), ""), "location": next((c["location"] for c in all_chunks
                      if c["chunk_id"] == item.get("chunk_id")), ""), "quote": item.get("quote", "")}
                      for item in saved["evidence"]], "warnings": saved["warnings"],
            "rule_checks": saved["rule_checks"], "judge": saved["judge"],
            "model_call_slots": saved["model_call_slots"],
            "actual_model_calls": 0 if model_mode == "fake" else sum(saved["model_call_slots"].values()),
            "tokens": saved["tokens"],
            "duration_ms": saved["duration_ms"]}


def evaluate(model_mode: str = "fake", only: set[str] | None = None, repeat: int = 1) -> dict[str, Any]:
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    if only:
        cases = [case for case in cases if case["id"] in only]
        missing = only - {case["id"] for case in cases}
        if missing:
            raise ValueError(f"알 수 없는 문항 ID: {', '.join(sorted(missing))}")
    results = []
    for iteration in range(1, repeat + 1):
        for case in cases:
            result = run_case(case, model_mode)
            result["iteration"] = iteration
            results.append(result)
    search_mode = "낱말 검색(임베딩 미설정)" if not embedding.enabled() else "벡터+낱말 검색(bge-m3)"
    return {"evaluation_date": EVALUATION_DATE.isoformat(), "model": model_mode,
            "search_mode": search_mode, "results": results,
            "total": len(results), "path_counts": dict(Counter(row["actual"]["actual_path"] for row in results)),
            "model_call_slots": dict(Counter(stage for row in results for stage, count in row["model_call_slots"].items()
                                              for _ in range(count))),
            "actual_model_calls": 0 if model_mode == "fake" else sum(
                row["actual_model_calls"] for row in results)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", choices=("fake", "real"), default="fake")
    parser.add_argument("--only", help="쉼표로 구분한 문항 ID")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--out", type=Path, help="결과 JSON 경로")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat는 1 이상이어야 합니다")
    _assert_isolated_test_database()
    selected = set(args.only.split(",")) if args.only else None
    result = evaluate(args.model, selected, args.repeat)
    print(json.dumps({key: result[key] for key in ("evaluation_date", "model", "search_mode", "total",
                                                   "path_counts", "model_call_slots", "actual_model_calls")},
                      ensure_ascii=False, indent=2))
    if args.out:
        output = args.out if args.out.is_absolute() else ROOT / args.out
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON: {output}")
    return 0


def _assert_isolated_test_database() -> None:
    """실수로 팀·공유 PostgreSQL에 접속하지 않도록 임시 DB만 허용한다."""
    database_url = os.getenv("DATABASE_URL")
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url or database_url != test_database_url or not os.getenv("TEST_DB_CONTAINER"):
        raise RuntimeError("tools/run_persona_eval.sh가 만든 임시 PostgreSQL에서만 실행할 수 있습니다")
    url = make_url(database_url)
    if url.host not in ("127.0.0.1", "localhost", "::1") or (url.port or 5432) == 5432:
        raise RuntimeError("임시 로컬 PostgreSQL 주소가 아닙니다. 실행을 중단합니다")


if __name__ == "__main__":
    raise SystemExit(main())
