"""기록 옵션이 없으면 DATABASE_URL·DB 연결 없이 기존 평가를 실행한다."""

import sys

import pytest

from app.core import db
from tests import fake_supervisor
from tools import eval_daily_note, eval_request


@pytest.mark.parametrize("tool", [eval_request, eval_daily_note], ids=["request", "daily_note"])
def test_eval_without_record_never_connects_to_database(tool, monkeypatch, capsys):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(sys, "argv", [tool.__file__])

    def forbidden():
        pytest.fail("[TEST] --record 없는 평가는 DB에 접근하면 안 된다")

    monkeypatch.setattr(db, "get_engine", forbidden)
    # 요청 평가의 RQ-20(판단 필요)은 낱말 대역이 아니라 가짜 감독 AI 답으로 판단 필요가 돼요.
    monkeypatch.setattr(eval_request, "classify", fake_supervisor.judged)
    assert tool.main() == (0 if tool is eval_request else None)
    output = capsys.readouterr()
    assert output.err == ""
    assert ("20/20 통과" if tool is eval_request else "모델 echo: 메모 함정") in output.out
