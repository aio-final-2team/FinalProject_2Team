"""[TEST] 가짜 감독 AI. 낱말 대역은 판단 필요를 만들지 않아서, 판단 필요 흐름 시험은 감독 결과를 이걸로 줘요.

본문에 MARK가 있으면 감독 AI가 판단 필요라고 답한 것처럼 하고, 없으면 모델 없음(빈 제안)처럼 해요.
실제 모델은 부르지 않아요.
"""

MARK = "판단 필요"
REASON = "[TEST] 교직원을 탓하는 글인지 확신이 낮아요"


def proposal(request_type, body, *args, **kwargs):
    return {"risk_level": "uncertain", "risk_category": None, "risk_reason": REASON} if MARK in body else {}


def install(monkeypatch):
    """mock 백엔드, DB 대역 입구(agent_stub), 협업 그래프(graph_agent가 supervisor에서 읽음)에 함께 끼워요."""
    from app.mock import store
    from app.modules.requests import agent_stub, supervisor

    monkeypatch.setattr(store, "_mock_proposal", lambda req: proposal(req.type, req.body))
    monkeypatch.setattr(agent_stub, "classify_request", proposal)
    monkeypatch.setattr(supervisor, "classify_request", proposal)


def judged(request_type, body):
    """가짜 감독 답을 실제 검증(validate_proposal)에 통과시킨 분류예요. 평가 도구의 낱말 분류 자리에 끼워요."""
    from app.modules.requests.supervisor import validate_proposal

    return validate_proposal(request_type, body, proposal(request_type, body))
