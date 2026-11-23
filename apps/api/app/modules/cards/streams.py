"""교직원 카드 스트림은 저장 이력의 단계와 현재 초안을 재생해요."""

from fastapi.responses import StreamingResponse

from app.modules.cards.card_views import detail
from app.modules.requests.streams import _encode


def stream(user, card_id):
    saved = detail(user, card_id)

    def events():
        stages = {"classified": "searching", "drafted": "drafting", "checked": "checking"}
        for event in saved["timeline"]:
            stage = stages.get(event["action"])
            if event["action"] == "created" and event["card_id"] is None and event["to_status"] == "received":
                stage = "classifying"
            if stage:
                yield _encode("stage", {"stage": stage, "at": event["created_at"]})
        card = saved["card"]
        draft = card["draft"].get("text", "")
        for offset in range(0, len(draft), 12):
            yield _encode("token", {"text": draft[offset : offset + 12]})
        yield _encode("card", {k: card[k] for k in ("id", "status", "version")})
        yield _encode("done", {"request_status": saved["request"]["status"] if saved["request"] else None})

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )
