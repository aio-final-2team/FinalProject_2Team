"""LangSmith 추적: 켜졌을 때만 모델 호출을 감싸고, 추적 준비가 실패해도 호출은 그대로 한다."""

import sys
import types

from agents import llm


def turn_on(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")


def test_tracing_needs_both_switch_and_key(monkeypatch):
    monkeypatch.delenv("LANGSMITH_TRACING", raising=False)
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)
    assert llm.tracing_on() is False
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    assert llm.tracing_on() is False
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")
    assert llm.tracing_on() is True
    monkeypatch.setenv("LANGSMITH_TRACING", "")
    assert llm.tracing_on() is False


def test_client_is_untouched_when_tracing_is_off(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "")
    client = object()
    assert llm.traced(client, "DOCUMENT", "gpt-test") is client


def test_client_is_wrapped_with_role_and_model_name(monkeypatch):
    turn_on(monkeypatch)
    seen = {}

    def wrap_openai(client, **options):
        seen.update(options, client=client)
        return "wrapped"

    monkeypatch.setitem(sys.modules, "langsmith", types.ModuleType("langsmith"))
    monkeypatch.setitem(sys.modules, "langsmith.wrappers", types.SimpleNamespace(wrap_openai=wrap_openai))
    client = object()
    assert llm.traced(client, "SUPERVISOR", "gpt-test") == "wrapped"
    assert seen["client"] is client
    assert seen["chat_name"] == "SUPERVISOR:gpt-test"
    assert seen["tracing_extra"] == {"tags": ["supervisor"], "metadata": {"role": "SUPERVISOR"}}


def test_call_goes_on_when_tracing_setup_fails(monkeypatch):
    turn_on(monkeypatch)

    def broken(client, **options):
        raise RuntimeError("추적 준비 실패")

    monkeypatch.setitem(sys.modules, "langsmith", types.ModuleType("langsmith"))
    monkeypatch.setitem(sys.modules, "langsmith.wrappers", types.SimpleNamespace(wrap_openai=broken))
    client = object()
    assert llm.traced(client, "CHECKER", "gpt-test") is client


def test_feature_runs_plainly_when_tracing_is_off(monkeypatch):
    monkeypatch.setenv("LANGSMITH_TRACING", "")

    @llm.feature("시험 기능")
    def work(value):
        return value + 1

    assert work(1) == 2
    assert work.__name__ == "work"


def test_feature_groups_under_its_name_without_inputs(monkeypatch):
    turn_on(monkeypatch)
    seen = {}

    def traceable(**options):
        seen.update(options)
        return lambda func: (lambda *args, **kwargs: ("묶음", func(*args, **kwargs)))

    monkeypatch.setitem(sys.modules, "langsmith", types.SimpleNamespace(traceable=traceable))

    @llm.feature("시험 기능")
    def work(value):
        return value + 1

    assert work(1) == ("묶음", 2)
    assert seen["name"] == "시험 기능"
    assert seen["process_inputs"]({"value": "학부모 글"}) == {}
    assert seen["process_outputs"]({"output": "답"}) == {}


def test_feature_does_not_run_twice_when_work_fails(monkeypatch):
    turn_on(monkeypatch)
    monkeypatch.setitem(sys.modules, "langsmith",
                        types.SimpleNamespace(traceable=lambda **options: (lambda func: func)))
    calls = []

    @llm.feature("시험 기능")
    def work():
        calls.append(1)
        raise ValueError("일하다 실패")

    try:
        work()
    except ValueError:
        pass
    assert calls == [1]


def test_keep_trace_carries_context_into_threads():
    import contextvars
    from concurrent.futures import ThreadPoolExecutor

    current = contextvars.ContextVar("current", default="없음")
    current.set("알림장 묶음")
    with ThreadPoolExecutor(max_workers=3) as pool:
        plain = list(pool.map(lambda _: current.get(), range(3)))
        kept = list(pool.map(llm.keep_trace(lambda _: current.get()), range(3)))
    assert plain == ["없음"] * 3
    assert kept == ["알림장 묶음"] * 3
