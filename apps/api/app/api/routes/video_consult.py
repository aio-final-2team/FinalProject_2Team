"""[제안][선택] WebRTC 신호만 중계해요. SDP·ICE는 저장하거나 기록하지 않아요."""

import asyncio
import json
from collections import deque
from time import monotonic
from uuid import UUID

import anyio
from fastapi import APIRouter, Depends, Response, WebSocket, WebSocketDisconnect

from app import backend
from app.api.schemas.common import errors
from app.api.schemas.video_consult import VideoRoom
from app.core import video_consult as rules
from app.core.auth import CurrentUser, current_user
from app.core.errors import ApiError, error_response

router = APIRouter(tags=["[선택] 화상상담"])
_rooms = {}  # API 프로세스 하나에서만 공유해요.
_lock = asyncio.Lock()
MAX_SIGNAL_BYTES = 64 * 1024
MAX_SIGNALS_PER_SECOND = 20


@router.get("/consultations/{booking_id}/room", response_model=VideoRoom,
            dependencies=[Depends(rules.enabled)], responses=errors(401, 403, 404, 409, 422),
            description="[제안][선택] FEATURE_VIDEO_CONSULT=true일 때 예약 담임·신청 보호자만 접속해요. "
                        "signal_path에 ?ticket=…로 WebSocket을 열어요. {type: offer|answer|ice|bye, data}만 "
                        "상대에게 전달해요(64KiB·초당 20개). 실패는 1008, 입퇴장은 peer_joined·peer_left예요.")
def room(booking_id: UUID, response: Response, user: CurrentUser = Depends(current_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return rules.room(user, booking_id)


async def send(peer, message):
    try:
        if isinstance(message, str):
            await peer.send_text(message)
        else:
            await peer.send_json(message)
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass  # 상대의 정리는 상대 receive 루프가 맡아요.


@router.websocket("/consultations/{booking_id}/signal")
async def signal(websocket: WebSocket, booking_id: str):
    if not rules.settings.feature_video_consult:
        await websocket.send_denial_response(error_response(websocket, 404, "NOT_FOUND"))
        return
    try:
        booking_id = UUID(booking_id)
        user = await anyio.to_thread.run_sync(rules.ticket_user, websocket.query_params.get("ticket", ""), booking_id)
        await anyio.to_thread.run_sync(backend.video_consult.access, user, booking_id)
    except (ApiError, ValueError):
        await websocket.close(code=1008, reason="access_denied")
        return
    joined = False
    try:
        async with _lock:
            await websocket.accept()
            peers = _rooms.setdefault(booking_id, {})
            old = peers.get(user.role)
            if old:
                try:
                    await old.close(code=1008, reason="replaced")
                except (WebSocketDisconnect, RuntimeError, OSError):
                    pass  # 이미 닫힌 옛 연결이어도 새 연결로 교체해요.
            peers[user.role] = websocket
            joined = True
            await anyio.to_thread.run_sync(backend.video_consult.record, user, booking_id, "video_joined")
            for role, peer in peers.items():
                if role != user.role:
                    await send(peer, {"type": "peer_joined"})
                    await send(websocket, {"type": "peer_joined"})
        received = deque()
        while True:
            frame = await websocket.receive()
            if frame["type"] == "websocket.disconnect":
                break
            raw = frame.get("text")
            tick = monotonic()
            while received and received[0] <= tick - 1:
                received.popleft()
            if raw is None or len(raw.encode("utf-8")) > MAX_SIGNAL_BYTES or len(received) >= MAX_SIGNALS_PER_SECOND:
                await websocket.close(code=1008, reason="signal_limit")
                break
            received.append(tick)
            try:
                def invalid_constant(value):
                    raise ValueError
                message = json.loads(raw, parse_constant=invalid_constant)
                if (not isinstance(message, dict) or set(message) != {"type", "data"}
                        or message["type"] not in ("offer", "answer", "ice", "bye")):
                    raise ValueError
            except (ValueError, TypeError, RecursionError):
                await websocket.close(code=1008, reason="invalid_signal")
                break
            async with _lock:
                peers = _rooms.get(booking_id, {})
                if peers.get(user.role) is not websocket:
                    break
                for role, peer in peers.items():
                    if role != user.role:
                        await send(peer, raw)
            if message["type"] == "bye":
                await websocket.close(code=1000)
                break
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        if joined:
            async with _lock:
                peers = _rooms.get(booking_id, {})
                if peers.get(user.role) is websocket:
                    del peers[user.role]
                    for peer in peers.values():
                        await send(peer, {"type": "peer_left"})
                    if not peers:
                        _rooms.pop(booking_id, None)
            await anyio.to_thread.run_sync(backend.video_consult.record, user, booking_id, "video_left")
