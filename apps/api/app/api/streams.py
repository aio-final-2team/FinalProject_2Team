"""학부모는 단계만, 교직원은 초안과 카드도 받는다."""

import asyncio
import json

from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.backend import store


def stream(req, card=None):
    async def events():
        sequence = [("stage", {"stage": step, "at": store.now()})
                    for step in ("classifying", "searching", "drafting", "checking")]
        if card:
            text = card.draft.get("text", "")
            sequence += [("token", {"text": text[i:i+12]}) for i in range(0, len(text), 12)]
            sequence.append(("card", {"id": card.id, "status": card.status, "version": card.version}))
        sequence.append(("done", {"request_status": req.status if req else None}))
        for index, (event, data) in enumerate(sequence):
            if index:
                await asyncio.sleep(settings.mock_stream_delay_ms / 1000)
            yield f"event: {event}\ndata: {json.dumps(jsonable_encoder(data), ensure_ascii=False)}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
