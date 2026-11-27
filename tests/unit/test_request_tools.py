"""[TEST] 예보·법령도 AI가 골라 부르는 도구예요. 인자 범위는 코드가 지키고, 공통 규칙엔 날것 자리표시가 없어요."""

import json
import re
from datetime import datetime, timedelta

import pytest

from agents.graphs import answer
from agents.llm import ModelError
from app.core.schedule import KST
from app.modules.documents import public_sources
from app.modules.documents.public_sources import FORECAST_DAYS, event_day, law_rule_key
from app.modules.documents.tools import RequestToolbox

ASKED = datetime(2026, 11, 27, 9, 0, tzinfo=KST)
FORECAST = {"chunk_id": 501, "quote": "11월 28일 예보", "score": 1.0, "document_title": "기상청 단기예보 2026-11-28",
            "location": "2026-11-28", "content": "11월 28일 예보: 최저 3도·최고 11도, 강수확률 최대 60%, 비 15시",
            "effective_from": None}
LAW = {"chunk_id": 601, "document_title": "학교보건법 제8조", "location": "제8조", "score": 1.0, "effective_from": None,
       "content": "학교보건법 제8조\n학교의 장은 감염병에 걸렸거나 걸릴 우려가 있는 학생에게 등교 중지를 명할 수 있다."}


def toolbox(kind="inquiry", body="[TEST] 내일 바깥 놀이 해요?"):
    return RequestToolbox({"type": kind, "body": body, "org_id": "org", "classroom_id": "class", "requester_id": "parent",
                           "child_id": None, "created_at": ASKED})


class Models:
    """역할마다 정해 둔 답을 돌려주고 받은 시스템 지시·입력을 남겨요."""

    def __init__(self, gather_calls, writer_ref, quote):
        self.gather_calls, self.writer_ref, self.quote, self.seen = gather_calls, writer_ref, quote, []

    def __call__(self, role):
        models = self

        class Model:
            def json(self, system, user):
                models.seen.append((role, system, json.loads(user)))
                if role == "GATHER":
                    found = json.loads(user)["found"]
                    return {"calls": [] if found else models.gather_calls, "done": bool(found)}
                if role == "CHECKER":
                    return {"passed": True, "issues": []}
                return {"text": "[TEST] 답", "evidence": [{**models.writer_ref, "quote": models.quote}],
                        "no_evidence": False, "conflict": False}
        return Model()


def run(monkeypatch, box, gather_calls, ref, quote, who=None):
    models = Models(gather_calls, ref, quote)
    monkeypatch.setattr(answer, "OpenAIModel", models)
    result = answer.draft_answer(box.req["body"], lambda *_: pytest.fail("고정 검색 금지"), gather_tools=box,
                                 today=ASKED.date(), who=who)
    return result, models


def test_forecast_tool_limits_dates_to_asked_day_and_forecast_window(monkeypatch):
    days = []
    monkeypatch.setattr(public_sources, "stored_forecast", lambda org, day: days.append(day) or FORECAST)
    box = toolbox()
    spec = next(s for s in box.specs() if s["name"] == "forecast")
    assert "기상청 단기예보" in spec["description"] and "언제" not in spec["description"]
    assert box.call("forecast", {"date": "2026-11-28"}) == [{k: v for k, v in FORECAST.items() if k != "quote"}]
    for bad in ({"date": "2026-11-26"}, {"date": str(ASKED.date() + timedelta(days=FORECAST_DAYS + 1))},
                {"date": "내일"}, {"date": "2026-11-28", "org_id": "다른 원"}, {}):
        with pytest.raises(ValueError):
            box.call("forecast", bad)
    assert days == [ASKED.date() + timedelta(days=1)]
    monkeypatch.setattr(public_sources, "stored_forecast", lambda org, day: None)
    assert box.call("forecast", {"date": "2026-11-27"}) == []  # 못 가져오면 빈 결과
    # 민원 도구에는 예보가 없고, 문의 도구에는 법령이 없어요.
    with pytest.raises(ValueError):
        toolbox("complaint").call("forecast", {"date": "2026-11-28"})
    with pytest.raises(ValueError):
        box.call("law_article", {"key": "infection"})


def test_law_tool_shows_table_without_when_words_and_rejects_unknown_keys(monkeypatch):
    monkeypatch.setattr(public_sources, "stored_law", lambda org, key: LAW if key == "infection" else None)
    box = toolbox("complaint")
    assert [s["name"] for s in box.specs()] == ["documents", "law_article"]
    spec = next(s for s in box.specs() if s["name"] == "law_article")
    for key, topic in public_sources.law_topics().items():
        assert f"{key}={topic['law_name']} {topic['article']}({topic['why']})" in spec["description"]
    assert not any(word in json.dumps(spec, ensure_ascii=False) for word in ("수족구", "독감", "risk_categories", "when"))
    for bad in ({"key": "fee"}, {"key": ["infection"]}, {"law": "infection"}, {}):
        with pytest.raises(ValueError):
            box.call("law_article", bad)
    assert box.call("law_article", {"key": "infection"}) == [LAW] and not box.law_unchecked
    assert box.call("law_article", {"key": "child_safety"}) == [] and box.law_unchecked


def test_agent_cites_forecast_and_law_without_trigger_words(monkeypatch):
    monkeypatch.setattr(public_sources, "stored_forecast", lambda org, day: FORECAST)
    box = toolbox()
    assert event_day(box.req["body"], ASKED.date()) is None  # 낱말 대역이라면 예보를 안 붙였을 질문
    result, _ = run(monkeypatch, box, [{"tool": "forecast", "args": {"date": "2026-11-28"}}],
                    {"chunk_id": 501}, "강수확률 최대 60%")
    assert [e["chunk_id"] for e in result["evidence"]] == [501] and result["gathered"] is True
    assert "law_unchecked" not in result

    body = "[TEST] 아이가 열이 나서 며칠 쉬었는데 언제 다시 가도 되나요"
    assert law_rule_key("health_hygiene", None, body) is None  # 낱말 조건에는 안 걸려요
    monkeypatch.setattr(public_sources, "stored_law", lambda org, key: LAW)
    result, _ = run(monkeypatch, toolbox("complaint", body), [{"tool": "law_article", "args": {"key": "infection"}}],
                    {"chunk_id": 601}, "등교 중지를 명할 수 있다")
    assert [e["chunk_id"] for e in result["evidence"]] == [601] and result["gathered"] is True


def test_law_tool_failure_marks_unchecked_on_answer(monkeypatch):
    class WithNotice(RequestToolbox):  # 법령을 못 가져와도 다른 근거로 초안을 쓰는 경우
        def specs(self):
            return [*super().specs(), {"name": "notice_stub", "description": "[TEST]", "args": {}}]

        def call(self, name, args):
            return [FORECAST] if name == "notice_stub" else super().call(name, args)

    monkeypatch.setattr(public_sources, "stored_law", lambda org, key: None)
    box = WithNotice(toolbox("complaint", "[TEST] 아동학대 아닌가요").req)
    result, _ = run(monkeypatch, box, [{"tool": "law_article", "args": {"key": "child_safety"}},
                                       {"tool": "notice_stub", "args": {}}], {"chunk_id": 501}, "강수확률")
    assert result["gathered"] is True and result["law_unchecked"] is True


def test_prompts_have_no_raw_placeholders_and_know_the_requested_child(monkeypatch):
    monkeypatch.setattr(public_sources, "stored_forecast", lambda org, day: FORECAST)
    _, models = run(monkeypatch, toolbox(), [{"tool": "forecast", "args": {"date": "2026-11-28"}}],
                    {"chunk_id": 501}, "강수확률 최대 60%", who={"role": "학부모(이 요청을 낸 보호자)", "child": "하늘"})
    assert [role for role, _, _ in models.seen] == ["GATHER", "GATHER", "DOCUMENT", "CHECKER"]
    for role, system, _ in models.seen:
        raw = set(re.findall(r"\{[a-z_]+\}", system))
        # 검사 AI 지침(checker.md, C 묶음)의 입력 칸 이름만 남아 있어요. 공통 규칙·자료 찾기·작성 지침엔 없어요.
        assert raw <= ({"{question}", "{draft}", "{evidence}", "{attempt}"} if role == "CHECKER" else set()), raw
        assert "- 오늘: 2026-11-27(금)" in system and "- 이 요청의 아이: 하늘 (요청한 보호자의 아이 1명)" in system
        assert "질문이 이 요청의 아이가 아닌 다른 아이를 묻는다면 그 아이 일은 답하지 않는다." in system
        assert "범위는 도구가 지킨다" in system
    # 아이를 모르는 경로(교직원 질문 등)는 그 줄을 빼요.
    plain = answer._common(ASKED.date())
    assert not re.search(r"\{[a-z_]+\}", plain) and "이 요청의 아이:" not in plain


def test_conflict_explanation_is_returned_only_when_asked_and_checked():
    chunks = [{"chunk_id": n, "content": f"겨울방학은 12월 {d}일에 시작해요.", "score": 0.9} for n, d in ((1, 24), (2, 26))]
    reply = {"text": "가정통신문은 12월 24일, 학사 일정표는 12월 26일로 적혀 있어요.", "no_evidence": False, "conflict": True,
             "evidence": [{"chunk_id": 1, "quote": "12월 24일"}, {"chunk_id": 2, "quote": "12월 26일"}]}

    class Writer:
        def json(self, system, user):
            return reply

    class Checker:
        def __init__(self, result):
            self.result, self.payloads = result, []

        def json(self, system, user):
            self.payloads.append(json.loads(user))
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

    search = lambda kind, query: chunks if kind == "notice" else []  # noqa: E731
    passed = Checker({"passed": True, "issues": []})
    result = answer.draft_answer("[TEST] 겨울방학", search, Writer(), passed, explain_conflict=True)
    assert result["conflict"] and result["text"] == reply["text"] and result["check_result"]["passed"]
    assert passed.payloads[0]["conflict"] is True and passed.payloads[0]["draft"] == reply["text"]
    # 받은함 경로는 지금처럼 고정 문구와 검사 실패 표시예요(검사 AI도 안 불러요).
    inbox = Checker({"passed": True, "issues": []})
    result = answer.draft_answer("[TEST] 겨울방학", search, Writer(), inbox)
    assert result["text"] == answer.NO_ANSWER and not result["check_result"]["passed"] and inbox.payloads == []
    for failed in ({"passed": False, "issues": [{"field": "출처", "problem": "[TEST] 날짜를 바꿔 옮겼어요"}]},
                   ModelError("[TEST]")):
        result = answer.draft_answer("[TEST] 겨울방학", search, Writer(), Checker(failed), explain_conflict=True)
        assert result["conflict"] and result["text"] == answer.NO_ANSWER and not result["check_result"]["passed"]
        assert len(result["evidence"]) == 2
