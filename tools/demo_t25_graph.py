"""T25 알림장 그래프를 가상 입력·가짜 모델로 실행하고 전후 비교를 남긴다.

    PYTHONPATH=. python tools/demo_t25_graph.py

API·DB·실제 OpenAI는 사용하지 않는다. 서버 전체 시연은 rehearse_daily_note.py를 쓴다.
"""

import json
import time
from pathlib import Path

from agents.graphs.daily_note import draft_daily_notes


OUTPUT = Path(__file__).resolve().parents[1] / "Docs/Step3/결과/T25_가상입력_전후비교.json"
UNSUPPORTED = "친구와 사이좋게 놀았어요."
CORRECTED = "점심을 조금 먹고 낮잠을 잘 잤어요."


class FakeWriter:
    def __init__(self):
        self.requests = 0

    def json(self, system, user):
        self.requests += 1
        return {"child": UNSUPPORTED if self.requests == 1 else CORRECTED, "requests": []}


class FakeChecker:
    def __init__(self):
        self.requests = 0

    def json(self, system, user):
        self.requests += 1
        if self.requests == 1:
            return {"checks": [{"item_key": "child", "kind": "not_in_memo",
                                "problem": "메모에 없는 문장", "sentence": UNSUPPORTED}]}
        return {"checks": []}


def main():
    payload = {
        "input_id": "t25-demo", "note_date": "2026-11-27", "classroom": "가상 별빛반",
        "activities": "블록 놀이를 했어요.", "supplies": "없음", "menu": None,
        "children": [{"child_id": "demo-child", "display_name": "가온",
                      "memo": "점심 조금 먹고 낮잠 잘 잠", "requests": []}],
    }
    writer, checker = FakeWriter(), FakeChecker()
    started = time.perf_counter()
    [result] = draft_daily_notes(payload, writer, checker, workers=1)
    seconds = round(time.perf_counter() - started, 4)
    trace = result["trace"]
    writes = [step["lines"][0]["value"] for step in trace if step["step"] == "write"]
    detected = next(step["kinds"] for step in trace if step["step"] == "check")
    returns = sum(step["step"] == "return" for step in trace)
    assert writes == [UNSUPPORTED, CORRECTED]
    assert detected == ["not_in_memo"] and result["end"] == "done" and returns == 1
    assert UNSUPPORTED not in str(result["content"])
    report = {
        "purpose": "12/4 자기 성찰 결과서용", "mode": "가상 입력·가짜 모델, 실제 OpenAI 호출 없음",
        "input_memo": payload["children"][0]["memo"],
        "first_draft": writes[0], "detected_checks": detected,
        "final_draft": writes[-1], "final_end": result["end"],
        "elapsed_seconds": seconds, "rewrite_count": returns,
        "model_requests": {"writer": writer.requests, "checker": checker.requests,
                           "transport_retries": 0, "format_reprompts": 0,
                           "total": writer.requests + checker.requests},
        "trace": trace,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{OUTPUT}: {report['final_end']}, 다시 쓰기 {returns}번, 모델 요청 {report['model_requests']['total']}번, {seconds:.4f}초")


if __name__ == "__main__":
    main()
