"""알림장 시연 리허설 스크립트를 DB 모드로 끝까지 돌린다(tools/rehearse_daily_note.py).

대역 작성기와, 가짜 모델을 붙인 실제 그래프 두 경우 모두 지아 한 명 때문에 반 발송이 막혔다가 풀려야 한다.
"""

from dataclasses import replace
from datetime import datetime
import json

import pytest

from agents.graphs import daily_note as graph
from agents.llm import OpenAIModel
from app.core.schedule import KST
from app.modules.daily_notes import runner
from db.seeds.demo import seed_demo
from tools.rehearse_daily_note import EDITED_LINE, rehearse


@pytest.fixture
def client(db_client, seeded_db):
    # 시연 날 아침처럼 보호자 요청 날짜를 오늘로 옮긴다.
    with seeded_db.begin() as connection:
        seed_demo(connection, refresh_note_requests=True)
    return db_client


def run(client):
    lines = []
    summary = rehearse(client, "teacher01", "demo1234", datetime.now(KST).date().isoformat(), out=lines.append)
    assert [line[:4] for line in lines if line.startswith("[")] == [f"[{n}] " if n < 10 else "[10]" for n in range(1, 11)]
    return summary


def test_rehearsal_with_stub_writer_blocks_on_jia_then_sends_whole_class(client):
    summary = run(client)
    assert summary["flagged"] == {"하늘": ["date_check", "sensitive"], "노을": ["request_missed"], "지아": ["sensitive"]}
    assert summary["blocked"] == {"지아": ["sensitive"]}
    assert summary["sent_count"] == 20
    assert summary["parent_notes"] == [("하늘", "sent")] and summary["parent_child_lines"] == [EDITED_LINE]


def test_rehearsal_with_graph_blocks_on_jia_even_when_checker_finds_nothing(client, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("[TEST] 실제 모델 호출 금지")

    class FakeModel:
        def __init__(self, answer):
            self.answer = answer

        def json(self, system, user):
            return self.answer(json.loads(user))

    # 자료 AI는 메모·요청을 그대로 옮기고 검사 AI는 아무것도 짚지 않는다. 남는 항목은 code_checks만 만든다.
    def echo(value):
        return {"child": value["child_memo"] or None,
                "requests": [{"request_id": r["request_id"], "value": r["text"]} for r in value["requests"]]}

    models = {"DOCUMENT": FakeModel(echo), "CHECKER": FakeModel(lambda value: {"checks": []})}
    monkeypatch.setattr(OpenAIModel, "json", forbidden)
    monkeypatch.setattr(graph, "OpenAIModel", lambda role: models[role])
    monkeypatch.setattr(runner, "settings", replace(runner.settings, daily_note_writer="graph"))
    summary = run(client)
    # 지아는 투약 요청, 지안은 메모의 다른 아이 이름(지아) 때문에 코드 규칙으로 걸린다.
    assert summary["flagged"] == {"지아": ["sensitive"], "지안": ["other_child"]}
    assert summary["blocked"] == {"지아": ["sensitive"]}
    assert summary["sent_count"] == 20
