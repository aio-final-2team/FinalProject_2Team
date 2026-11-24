"""요청 평가 20문항을 가짜 모델로 옛·새 그래프에 돌린다."""

import json

from tools.eval_request import CASES, evaluate


def test_request_cases_have_expected_counts_and_fields():
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 20 and len({case["id"] for case in cases}) == 20
    assert sum(case["request_type"] == "inquiry" for case in cases) == 12
    assert sum(case["expected_route"] == "complaint" for case in cases) == 6
    assert sum(case["expected_route"] == "high_risk" for case in cases) == 2
    assert all({"body", "request_type", "expected_route", "expected_evidence_title", "no_evidence"} <= case.keys()
               for case in cases)
    assert all("risk_level" not in case for case in cases)


def test_fake_model_compares_all_old_and_new_request_cases():
    results = evaluate()
    assert len(results) == 20 and all(item["passed"] for item in results)
    assert all(not item["differences"] for item in results[:12])
    assert all(item["old"]["card_kind"] == item["new"]["card_kind"] for item in results)
    assert all(item["old"]["status"] == item["new"]["status"] for item in results)
    assert all("evidence_titles" in item["differences"] for item in results[12:17])
