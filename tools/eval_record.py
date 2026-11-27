"""평가 실행기가 명시적으로 요청했을 때만 기존 eval_runs에 한 줄을 남긴다."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps/api"))


def record_run(*, tool, model, started_at, total, passed, report_url=None, scores=None):
    from sqlalchemy import text

    from agents.llm import model_name
    from app.core.db import transaction

    real = model == "openai"
    note = {"tool": tool, "checker_model": model_name("CHECKER") if real else model, **(scores or {})}
    with transaction() as connection:
        connection.execute(text("""
            INSERT INTO eval_runs (suite,requested_model,started_at,total,passed,report_url,note)
            VALUES ('service',:model,:started,:total,:passed,:report,:note)
        """), {"model": model_name("DOCUMENT") if real else model, "started": started_at,
               "total": total, "passed": passed, "report": str(report_url) if report_url else None,
               "note": json.dumps(note, ensure_ascii=False)})
