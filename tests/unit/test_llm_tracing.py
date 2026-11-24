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
