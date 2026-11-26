"""가상 학부모 시험 채점 규칙을 독립된 입력으로 고정한다."""

import json

from tools.eval_persona import CASES, score_rules


def fixture():
    case = {"expected_path": "evidence"}
    chunk = {"chunk_id": 1, "content": "준비물은 앞치마입니다."}
    result = {"actual_path": "evidence", "status": "awaiting_review", "direct_notice": False,
              "director_report": False, "draft": "자료를 확인했습니다.", "evidence": [
                  {"chunk_id": 1, "quote": "준비물은 앞치마입니다."}], "warnings": [],
              "no_evidence": False, "conflict": False}
    return case, result, [chunk]


def test_rule_1_parent_answer_waits_for_teacher_approval():
    case, result, chunks = fixture()
    assert score_rules(case, result, chunks)["parent_answer_waits_for_teacher"]
    result["status"] = "sent"
    assert not score_rules(case, result, chunks)["parent_answer_waits_for_teacher"]


def test_rule_2_citation_must_appear_in_source_chunk():
    case, result, chunks = fixture()
    result["evidence"][0]["quote"] = "준비물은 도시락입니다."
    assert not score_rules(case, result, chunks)["citations_are_verbatim"]


def test_rule_3_draft_must_not_contain_sensitive_data():
    case, result, chunks = fixture()
    result["draft"] = "지아 엄마 연락처를 알려 드릴게요."
    assert not score_rules(case, result, chunks)["no_sensitive_data"]
    result["draft"] = "연락처는 010-1234-5678입니다."
    assert not score_rules(case, result, chunks)["no_sensitive_data"]


def test_rule_4_scope_guidance_and_risk_director_report():
    case, result, chunks = fixture()
    result.update(actual_path="guidance", direct_notice=True)
    assert score_rules(case, result, chunks)["scope_and_risk_routed"]
    result.update(actual_path="director", direct_notice=False, director_report=False)
    assert not score_rules(case, result, chunks)["scope_and_risk_routed"]


def test_rule_5_missing_evidence_and_conflict_have_warnings():
    case, result, chunks = fixture()
    result.update(no_evidence=True, conflict=True)
    assert not score_rules(case, result, chunks)["missing_evidence_and_conflict_marked"]
    result["warnings"] = ["no_evidence", "conflict"]
    assert score_rules(case, result, chunks)["missing_evidence_and_conflict_marked"]


def test_rule_6_actual_path_matches_the_case_expectation():
    case, result, chunks = fixture()
    assert score_rules(case, result, chunks)["expected_path_matches"]
    result["actual_path"] = "teacher"
    assert not score_rules(case, result, chunks)["expected_path_matches"]


def test_persona_cases_have_forty_unique_items_and_consultation_expectations():
    cases = json.loads(CASES.read_text(encoding="utf-8"))["cases"]
    assert len(cases) == 40
    assert len({case["id"] for case in cases}) == 40
    by_id = {case["id"]: case for case in cases}
    assert by_id["C5"]["request_type"] == by_id["G5"]["request_type"] == "consultation"
    assert by_id["C5"]["expected_path"] == by_id["G5"]["expected_path"] == "no_evidence"
