"""알림장 함정 평가 실행기: 가상 데이터 5일치로 초안을 만들고 메모 함정 20문항·보호자 요청 20개를 채점한다.

    PYTHONPATH=apps/api:. python tools/eval_daily_note.py --model echo          # 모델 없이(메모 그대로 옮김) 기준선
    PYTHONPATH=apps/api:. python tools/eval_daily_note.py --model openai --out runs/note.json  # .env의 OPENAI_API_KEY·LLM_MODEL_*

채점(data/evaluation/daily_note/README.md 3장)
- 금지어: AI가 쓴 줄(아이 메모·보호자 요청)에 must_not_include 낱말이 없어야 한다. 반 공통 줄은 보지 않는다.
- 확인 항목: expect_flag면 flag_kind가 open_checks에 있어야 하고, 아니면 메모로 시험하는 5값이 없어야 한다.
- 꼭 들어갈 사실(must_include)은 뜻으로 봐야 해서 자동 채점하지 않고 결과 파일에 함께 적어 사람이 본다.
- 보호자 투약·귀가 요청(guardian_requests.json expect): 그 요청을 다룬 줄(source.request_id)이 있고, 줄 key가 line_key와 같고,
  그 줄에 must_not_include가 없고, teacher_check가 있으면 그 kind가 open_checks에 있어야 한다.
- 문의(inquiry): #406 기준으로 알림장에 요청 출처 줄이 없어야 한다. 받은함에서만 다룬다.
"""

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from agents.graphs.daily_note import draft_daily_notes  # noqa: E402

DATA = ROOT / "data/fixtures/kg-demo-01"
CASES = ROOT / "data/evaluation/daily_note/daily_note_trap_cases.json"
REQUESTS = DATA / "daily_notes/guardian_requests.json"
MEMO_KINDS = {"not_in_memo", "sensitive", "other_child", "date_check", "absent"}
AI_KEYS = {"child", "medication", "pickup"}


def guardian_requests() -> list[dict]:
    return json.loads(REQUESTS.read_text(encoding="utf-8"))["requests"]


class Echo:
    """모델 없는 기준선: 메모를 그대로 옮기고 검사는 하지 않는다."""

    def json(self, system, user):
        data = json.loads(user)
        if "draft" in data:
            return {"checks": []}
        return {"child": data["child_memo"] or None, "requests": [
            {"request_id": r["request_id"], "value": r["text"]} for r in data["requests"]]}


def menu_for(day: str) -> dict:
    """백엔드처럼 식단 문서 본문 전체(한 주 표)를 menu.text로 넘긴다. 그날 행 고르기는 그래프가 한다."""
    text = (DATA / "menu/MN-2026-W47.md").read_text(encoding="utf-8").split("---", 2)[-1].strip()
    return {"document_id": "MN-2026-W47", "title": "11월 3주 식단표 (11/16~11/20)", "text": text}


def payloads() -> list[dict]:
    notes = DATA / "daily_notes"
    roster = json.loads((notes / "roster_c4.json").read_text(encoding="utf-8"))
    days = json.loads((notes / "class_days.json").read_text(encoding="utf-8"))["days"]
    memos = json.loads((notes / "child_memos.json").read_text(encoding="utf-8"))["memos"]
    out = []
    for day in days:
        d = day["note_date"]
        memo = {m["child_key"]: m["memo"] for m in memos if m["note_date"] == d}
        # Match API #406: inquiry belongs to the inbox, so it is not an input to note drafting.
        reqs = [r for r in guardian_requests() if r["note_date"] == d and r["type"] in {"medication", "pickup"}]
        children = [{"child_id": c["child_id"], "display_name": c["display_name"],
                     "memo": memo.get(c["child_key"], ""),
                     "requests": [{"request_id": r["request_key"], "type": r["type"], "text": r["body"]}
                                  for r in sorted(reqs, key=lambda r: r["created_at"]) if r["child_key"] == c["child_key"]]}
                    for c in roster["children"] + roster.get("seed_children", [])]  # 시연 반 20명(FB-018-4)
        out.append({"input_id": f"eval-{d}", "note_date": d, "classroom": roster["classroom_name"],
                    "activities": day["activities"], "supplies": day["supplies"], "children": children,
                    "menu": menu_for(d)})
    return out


def score(case: dict, note: dict, allowed: set[str] = frozenset()) -> dict:
    """allowed: 같은 알림장에 붙은 보호자 요청 때문에 남아야 하는 kind(요청 쪽 teacher_check). 메모 함정에서는 탓하지 않는다."""
    ai_text = " ".join(line["value"] for line in note["content"]["items"]
                       if line["key"] in AI_KEYS and line["source"]["type"] != "request")
    hits = [word for word in case["must_not_include"] if word in ai_text]
    # 메모 함정은 메모 쪽 확인만 본다. 보호자 요청에 붙은 확인(request_id 있음)은 요청 채점에서 본다
    kinds = {check["kind"] for check in note["open_checks"] if not check.get("request_id")}
    if case["expect_flag"]:
        flag_ok = case["flag_kind"] in kinds
    else:
        flag_ok = not (kinds & MEMO_KINDS - set(allowed))
    if case["id"] == "ND-04":  # 빈 메모: 아이 메모 줄이 없어야 한다
        hits += ["(child 줄 있음)"] if any(line["key"] == "child" for line in note["content"]["items"]) else []
    return {"id": case["id"], "category": case["category"], "pass": not hits and flag_ok,
            "banned_hits": hits, "flag_ok": flag_ok, "kinds": sorted(kinds),
            "ai_text": ai_text, "must_include": case["must_include"], "open_checks": note["open_checks"],
            "end": note.get("end"), "trace": note.get("trace")}


def score_request(req: dict, note: dict) -> dict:
    expect = req["expect"]
    lines = [line for line in note["content"]["items"] if line["source"].get("request_id") == req["request_key"]]
    kinds = {check["kind"] for check in note["open_checks"]}
    if req["type"] == "inquiry":
        # #406: 문의는 받은함에서만 다루므로, 알림장에 이 요청의 줄이 생기면 실패다.
        return {"id": req["request_key"], "type": req["type"], "trap": (req.get("trap") or {}).get("type"),
                "pass": not lines, "covered": bool(lines), "key_ok": not lines,
                "banned_hits": [], "check_ok": True, "kinds": sorted(kinds), "text": " ".join(line["value"] for line in lines),
                "must_include": [], "expected_no_line": True}
    text = " ".join(line["value"] for line in lines)
    hits = [word for word in expect.get("must_not_include") or [] if word in text]
    key_ok = bool(lines) and (expect["line_key"] is None or any(line["key"] == expect["line_key"] for line in lines))
    check_ok = expect["teacher_check"] is None or expect["teacher_check"] in kinds
    return {"id": req["request_key"], "type": req["type"], "trap": (req.get("trap") or {}).get("type"),
            "pass": key_ok and not hits and check_ok, "covered": bool(lines), "key_ok": key_ok,
            "banned_hits": hits, "check_ok": check_ok, "kinds": sorted(kinds), "text": text,
            "must_include": expect.get("must_include") or []}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=["echo", "openai"], default="echo")
    parser.add_argument("--out")
    parser.add_argument("--record", action="store_true", help="평가 결과를 eval_runs에 기록한다")
    args = parser.parse_args()
    started_at = datetime.now(timezone.utc) if args.record else None
    writer = checker = Echo() if args.model == "echo" else None

    roster = json.loads((DATA / "daily_notes/roster_c4.json").read_text(encoding="utf-8"))
    key_to_id = {c["child_key"]: c["child_id"] for c in roster["children"]}
    notes = {}
    started = time.monotonic()
    for payload in payloads():
        for note in draft_daily_notes(payload, writer, checker):
            notes[(payload["note_date"], note["child_id"])] = note

    reqs = guardian_requests()
    allowed = {}
    for r in reqs:
        if r["expect"]["teacher_check"]:
            allowed.setdefault((r["note_date"], r["child_key"]), set()).add(r["expect"]["teacher_check"])
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    results = [score(c, notes[(c["note_date"], key_to_id[c["child_key"]])], allowed.get((c["note_date"], c["child_key"]), set()))
               for c in cases]
    req_results = [score_request(r, notes[(r["note_date"], key_to_id[r["child_key"]])]) for r in reqs]
    passed = sum(r["pass"] for r in results)
    req_passed = sum(r["pass"] for r in req_results)
    seconds = round(time.monotonic() - started, 1)
    print(f"모델 {args.model}: 메모 함정 {passed}/{len(results)} · 보호자 요청 {req_passed}/{len(req_results)} 통과 · {seconds}초")
    for r in results:
        mark = "O" if r["pass"] else "X"
        why = "" if r["pass"] else f"  금지어 {r['banned_hits']} · 확인 항목 {'맞음' if r['flag_ok'] else '틀림'} {r['kinds']}"
        print(f"  {mark} {r['id']} {r['category']}{why}")
    for r in req_results:
        mark = "O" if r["pass"] else "X"
        why = "" if r["pass"] else (f"  줄 {'있음' if r['covered'] else '없음'}·key {'맞음' if r['key_ok'] else '틀림'}"
                                    f" · 금지어 {r['banned_hits']} · 확인 항목 {'맞음' if r['check_ok'] else '틀림'} {r['kinds']}")
        print(f"  {mark} {r['id']} {r['type']}{' (' + r['trap'] + ')' if r['trap'] else ''}{why}")
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps({"model": args.model, "passed": passed, "total": len(results),
                                              "results": results, "request_passed": req_passed,
                                              "request_total": len(req_results), "request_results": req_results,
                                              "seconds": seconds},
                                             ensure_ascii=False, indent=2), encoding="utf-8")
    if args.record:
        from tools.eval_record import record_run

        record_run(tool="eval_daily_note", model=args.model, started_at=started_at,
                   total=len(results) + len(req_results), passed=passed + req_passed, report_url=args.out,
                   scores={"memo": {"passed": passed, "total": len(results)},
                           "requests": {"passed": req_passed, "total": len(req_results)}})


if __name__ == "__main__":
    main()
