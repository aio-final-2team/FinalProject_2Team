"""두 평가 CLI의 선택 기록·점수·모델 정보가 기존 표에 그대로 저장되는지 본다."""

import json
import sys
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from tools import eval_daily_note, eval_request

TOOLS = [eval_request, eval_daily_note]


@pytest.fixture(params=TOOLS, ids=["request", "daily_note"])
def tool(request, monkeypatch):
    # 실제 모델 호출은 어떤 경로에서도 허용하지 않는다.
    from agents.llm import OpenAIModel

    def forbidden(*args, **kwargs):
        pytest.fail("[TEST] 실제 모델 호출 금지")

    monkeypatch.setattr(OpenAIModel, "_call", forbidden)
    # 알림장 출력·보고서의 소요 시간도 두 실행에서 같게 맞춘다.
    monkeypatch.setattr(eval_daily_note, "time", SimpleNamespace(monotonic=lambda: 100.0))
    return request.param


def rows(engine):
    with engine.connect() as connection:
        return {r["id"]: dict(r) for r in connection.execute(text("SELECT * FROM eval_runs")).mappings()}


def run(tool, monkeypatch, output, *args):
    out_args = ["--out", str(output)] if output is not None else []
    monkeypatch.setattr(sys, "argv", [tool.__file__, *out_args, *args])
    return tool.main()


def test_eval_record_is_opt_in_one_row_and_preserves_output(tool, seeded_db, monkeypatch, tmp_path, capsys):
    before = rows(seeded_db)
    output = tmp_path / "report.json"
    code = run(tool, monkeypatch, output)
    stdout = capsys.readouterr()
    report = output.read_bytes()
    assert rows(seeded_db) == before

    started = datetime.now(timezone.utc)
    assert run(tool, monkeypatch, output, "--record") == code
    ended = datetime.now(timezone.utc)
    assert capsys.readouterr() == stdout and output.read_bytes() == report
    after = rows(seeded_db)
    assert all(after[key] == value for key, value in before.items())
    assert len(after) == len(before) + 1
    row, = [r for key, r in after.items() if key not in before]
    data = json.loads(report)
    assert row["suite"] == "service"
    assert row["total"] == data["total"] + data.get("request_total", 0)
    assert row["passed"] == data["passed"] + data.get("request_passed", 0)
    assert row["requested_model"] == ("fake" if tool is eval_request else "echo")
    assert row["returned_model"] is None and row["errors"] == 0
    assert row["report_url"] == str(output)
    assert started <= row["started_at"] <= ended
    assert row["created_at"] >= row["started_at"]
    note = json.loads(row["note"])
    assert note["tool"] == tool.__name__.split(".")[-1]
    assert note["checker_model"] == row["requested_model"]
    if tool is eval_daily_note:
        assert note["memo"] == {"passed": data["passed"], "total": data["total"]}
        assert note["requests"] == {"passed": data["request_passed"], "total": data["request_total"]}


def test_eval_record_real_model_names_and_failed_scores(tool, seeded_db, monkeypatch):
    monkeypatch.setenv("LLM_MODEL_DEFAULT", "[TEST] default-model")
    monkeypatch.setenv("LLM_MODEL_DOCUMENT", "[TEST] document-model")
    monkeypatch.setenv("LLM_MODEL_CHECKER", "[TEST] checker-model")
    if tool is eval_request:
        monkeypatch.setattr(eval_request.answer, "OpenAIModel", lambda role: eval_request.FakeModel())
        evaluate = tool.evaluate

        def failing(**kwargs):
            results = evaluate(**kwargs)
            results[0]["passed"] = False
            return results

        monkeypatch.setattr(tool, "evaluate", failing)
        args = ["--real"]
    else:
        from agents.graphs import daily_note

        monkeypatch.setattr(daily_note, "OpenAIModel", lambda role: eval_daily_note.Echo())
        score = tool.score

        def failing(case, *args):
            result = score(case, *args)
            if case["id"] == "ND-01":
                result["pass"] = False
            return result

        monkeypatch.setattr(tool, "score", failing)
        args = ["--model", "openai"]
    before = rows(seeded_db)
    code = run(tool, monkeypatch, None, "--record", *args)
    # 요청의 실패 종료값과 알림장의 기존 None 반환도 유지한다.
    assert code == (1 if tool is eval_request else None)
    row, = [r for key, r in rows(seeded_db).items() if key not in before]
    assert row["requested_model"] == "[TEST] document-model"
    assert json.loads(row["note"])["checker_model"] == "[TEST] checker-model"
    assert row["passed"] < row["total"] and row["errors"] == 0
    assert row["returned_model"] is None
    assert row["report_url"] is None


def test_eval_record_database_failure_is_reported(tool, seeded_db, monkeypatch, tmp_path):
    from app.core import db

    before = rows(seeded_db)

    def unavailable():
        raise RuntimeError("[TEST] 평가 기록 DB 연결 실패")

    monkeypatch.setattr(db, "transaction", unavailable)
    output = tmp_path / "report.json"
    with pytest.raises(RuntimeError, match="평가 기록 DB 연결 실패"):
        run(tool, monkeypatch, output, "--record")
    assert output.exists() and rows(seeded_db) == before
