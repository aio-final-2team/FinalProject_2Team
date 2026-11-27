"""요청 20문항을 옛·새 그래프와 가짜 모델로 비교한다.

PYTHONPATH=apps/api:. python tools/eval_request.py
PYTHONPATH=apps/api:. python tools/eval_request.py --real  # 실제 모델 호출: 별도 허가를 받고 실행
"""

import argparse
import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

from langgraph.checkpoint.memory import InMemorySaver

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps/api"))

from agents.graphs import answer  # noqa: E402
from agents.graphs.request import build_graph as build_old  # noqa: E402
from agents.graphs.request_collaboration import build_graph as build_new  # noqa: E402
from app.core.request_rules import classify  # noqa: E402
from app.modules.documents.parsing import parse_document  # noqa: E402
from app.modules.documents.search import score, terms  # noqa: E402

CASES = ROOT / "data/evaluation/request/request_cases.json"
FIXTURES = ROOT / "data/fixtures/kg-demo-01"
EVAL_DATE = date(2026, 12, 2)


class FakeModel:
    """가장 점수가 높은 원 자료 조각만 인용하는 재현 가능한 모델 대역."""

    def json(self, system, user):
        payload = json.loads(user)
        if "draft" in payload:
            return {"passed": True, "issues": []}
        chunks = payload["chunks"]
        if not chunks:
            return {"text": "", "evidence": [], "no_evidence": True, "conflict": False}
        chunk = chunks[0]
        quote = next((line.strip()[:30] for line in chunk["content"].splitlines() if line.strip()), "")
        return {"text": "자료를 확인했습니다.", "evidence": [{"chunk_id": chunk["chunk_id"], "quote": quote}],
                "no_evidence": False, "conflict": False}


def documents():
    chunks = []
    for folder in ("notice", "schedule", "menu", "policy"):
        for path in sorted((FIXTURES / folder).glob("*.md")):
            parsed = parse_document(path.read_text(encoding="utf-8"))
            meta = parsed.meta
            if meta.effective_from > EVAL_DATE or (meta.classroom_keys and "C4" not in meta.classroom_keys):
                continue
            for chunk in parsed.chunks:
                chunks.append({"chunk_id": len(chunks) + 1, "document_title": meta.title,
                               "doc_type": meta.doc_type, "location": chunk.location,
                               "content": chunk.content})
    return chunks


def search(chunks, doc_type, question):
    words = terms(question)
    found = [{**chunk, "score": score(words, chunk["document_title"], chunk["location"], chunk["content"])}
             for chunk in chunks if chunk["doc_type"] == doc_type]
    return sorted((chunk for chunk in found if chunk["score"] > 0),
                  key=lambda chunk: (-chunk["score"], chunk["chunk_id"]))[:8]


def candidates(chunks, case):
    types = ("notice", "policy") if case["request_type"] == "complaint" else ("notice", "schedule", "menu", "policy")
    found = [chunk for doc_type in types for chunk in search(chunks, doc_type, case["body"])]
    return sorted(found, key=lambda chunk: (-chunk["score"], chunk["chunk_id"]))[:8]


def run_case(case, graph_kind, chunks, real=False):
    model = answer.OpenAIModel("DOCUMENT") if real else FakeModel()
    checker_model = answer.OpenAIModel("CHECKER") if real else FakeModel()
    picked = candidates(chunks, case)
    high_risk = classify(case["request_type"], case["body"]).get("risk_level") in ("urgent", "uncertain")
    saved = {}

    def card(request_id, route, result=None, classification=None):
        if high_risk:
            result = {"text": "", "evidence": [], "no_evidence": True}
        elif result is None and route == "inquiry":
            result = answer.draft_answer(case["body"], lambda kind, _: search(chunks, kind, case["body"]),
                                         writer=model, checker=checker_model)
        elif result is None:
            result = {"text": "(모의 초안)", "evidence": [], "no_evidence": True}
        if result.get("no_evidence") or result.get("conflict"):
            result = {**result, "text": ""}
        saved.update({"route": "high_risk" if high_risk else route, "card_kind": "reply_draft",
                      "status": "escalated" if high_risk else "awaiting_review",
                      "evidence_titles": sorted({next(chunk["document_title"] for chunk in chunks
                                                       if chunk["chunk_id"] == item["chunk_id"])
                                                 for item in result.get("evidence", [])}),
                      "no_evidence": bool(result.get("no_evidence")),
                      "handoff_reason": "high_risk" if high_risk else "no_evidence" if result.get("no_evidence") else ""})
        return "card-1"

    if graph_kind == "old":
        graph = build_old(InMemorySaver(), lambda _: case["request_type"],
                          lambda request_id, route: card(request_id, route), lambda _: "pending")
    else:
        def write(state):
            reply = answer._ask_writer(model, answer.WRITE_FORMAT,
                                       {"question": case["body"], "chunks": state["parallel"]["chunks"],
                                        "review_issues": state.get("issues", [])}, [])
            return {"draft": answer._verify(reply, picked, []) if reply else
                    {"text": "", "evidence": [], "no_evidence": True, "conflict": False}}

        def check(state):
            issues = answer._review(checker_model, case["body"], state["draft"], picked,
                                    state.get("attempt", 0) + 1, [])
            return {"passed": issues == [], "issues": issues or []}

        graph = build_new(InMemorySaver(), lambda _: case["request_type"], card, lambda _: "pending",
                          search=lambda _: picked, load_memory=lambda _: [], write=write, check=check,
                          high_risk=lambda _: {"risk_level": "urgent" if high_risk else "normal"})
    graph.invoke({"request_id": case["id"]}, {"configurable": {"thread_id": f"{graph_kind}:{case['id']}"}})
    return saved


def evaluate(real=False):
    chunks = documents()
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    results = []
    for case in cases:
        old, new = (run_case(case, kind, chunks, real=real) for kind in ("old", "new"))
        expected = case["expected_evidence_title"]
        passed = (new["route"] == case["expected_route"] and new["card_kind"] == "reply_draft"
                  and new["no_evidence"] == case["no_evidence"]
                  and (expected is None or expected in new["evidence_titles"])
                  and old["route"] == new["route"] and old["card_kind"] == new["card_kind"]
                  and old["status"] == new["status"])
        differences = [key for key in ("evidence_titles", "no_evidence", "handoff_reason") if old[key] != new[key]]
        results.append({"id": case["id"], "type": case["request_type"], "passed": passed,
                        "old": old, "new": new, "differences": differences})
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--real", action="store_true", help="실제 모델을 호출한다")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--record", action="store_true", help="평가 결과를 eval_runs에 기록한다")
    args = parser.parse_args()
    started_at = datetime.now(timezone.utc) if args.record else None
    results = evaluate(real=args.real)
    print("문항 | 유형 | 옛 분기/카드/근거 | 새 분기/카드/근거 | 차이 | 결과")
    for item in results:
        old, new = item["old"], item["new"]
        def fmt(row):
            return f"{row['route']}/{row['card_kind']}/{','.join(row['evidence_titles']) or '-'}"
        print(f"{item['id']} | {item['type']} | {fmt(old)} | {fmt(new)} | "
              f"{','.join(item['differences']) or '-'} | {'통과' if item['passed'] else '실패'}")
    passed = sum(item["passed"] for item in results)
    print(f"{passed}/{len(results)} 통과")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps({"results": results, "passed": passed, "total": len(results)},
                                       ensure_ascii=False, indent=2), encoding="utf-8")
    if args.record:
        from tools.eval_record import record_run

        record_run(tool="eval_request", model="openai" if args.real else "fake", started_at=started_at,
                   total=len(results), passed=passed, report_url=args.out)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
