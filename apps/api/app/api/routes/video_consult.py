"""[제안][선택] WebRTC 신호만 중계해요. SDP·ICE는 저장하거나 기록하지 않아요."""

import asyncio
import json
from collections import deque
from dataclasses import dataclass, field
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


@dataclass
class Room:
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    peers: dict = field(default_factory=dict)
    users: int = 0


SEND_TIMEOUT = 2
RECHECK_SECONDS = 10
MAX_SIGNAL_BYTES = 64 * 1024
MAX_SIGNALS_PER_SECOND = 20


@router.get("/consultations/{booking_id}/room", response_model=VideoRoom,
            dependencies=[Depends(rules.enabled)], responses=errors(401, 403, 404, 409, 422),
            description="[제안][선택] FEATURE_VIDEO_CONSULT=true일 때 예약 담임·신청 보호자만 접속해요. "
                        "signal_path에 ?ticket=…로 WebSocket을 열어요. {type: offer|answer|ice|bye, data}만 "
                        "상대에게 전달해요(64KiB·초당 20개). ticket은 일회용이고, 켠 상태의 거부는 수락 뒤 1008이에요. "
                        "10초 간격으로 메시지 전 권한을 다시 보고 closes_at에 조용한 연결도 닫아요. "
                        "서버가 닫으면 화면은 RTCPeerConnection을 닫아요. 입퇴장은 peer_joined·peer_left예요.")
def room(booking_id: UUID, response: Response, user: CurrentUser = Depends(current_user)):
    response.headers["Cache-Control"] = "private, no-store"
    return rules.room(user, booking_id)


async def close(peer, reason, code=1008):
    try:
        await asyncio.wait_for(peer.close(code=code, reason=reason), SEND_TIMEOUT)
    except (TimeoutError, WebSocketDisconnect, RuntimeError, OSError):
        pass


async def send(peer, message):
    try:
        operation = peer.send_text(message) if isinstance(message, str) else peer.send_json(message)
        await asyncio.wait_for(operation, SEND_TIMEOUT)
    except TimeoutError:
        await close(peer, "slow_peer")
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass  # 상대의 정리는 상대 receive 루프가 맡아요.


@router.websocket("/consultations/{booking_id}/signal")
async def signal(websocket: WebSocket, booking_id: str):
    if not rules.settings.feature_video_consult:
        await websocket.send_denial_response(error_response(websocket, 404, "NOT_FOUND"))
        return
    rules.install_log_filter()
    try:
        booking_id = UUID(booking_id)
        user, claims = await anyio.to_thread.run_sync(rules.ticket_user, websocket.query_params.get("ticket", ""), booking_id)
        row = await anyio.to_thread.run_sync(backend.video_consult.access, user, booking_id)
    except (ApiError, ValueError):
        await websocket.accept()
        await close(websocket, "access_denied")
        return
    state = _rooms.setdefault(booking_id, Room())
    state.users += 1  # 정리 중인 방에 새 연결이 들어와도 같은 잠금을 써요.
    joined = False
    try:
        await websocket.accept()
        async with state.lock:
            old = state.peers.get(user.role)
            state.peers[user.role] = websocket
            peers = [peer for role, peer in state.peers.items() if role != user.role]
            joined = True
        if old:
            await close(old, "replaced")
        await anyio.to_thread.run_sync(backend.video_consult.record, user, booking_id, "video_joined")
        for peer in peers:
            await send(peer, {"type": "peer_joined"})
            await send(websocket, {"type": "peer_joined"})
        checked_at = monotonic()
        received = deque()
        while True:
            remaining = (row["closes_at"] - rules.now()).total_seconds()
            try:
                frame = await asyncio.wait_for(websocket.receive(), max(0, remaining))
            except TimeoutError:
                await close(websocket, "room_closed")
                break
            if frame["type"] == "websocket.disconnect":
                break
            tick = monotonic()
            if tick - checked_at >= RECHECK_SECONDS:
                try:
                    await anyio.to_thread.run_sync(rules.recheck_user, claims)
                    row = await anyio.to_thread.run_sync(backend.video_consult.access, user, booking_id)
                except ApiError as error:
                    reason = "room_closed" if error.details.get("reason") == "room_closed" else "access_denied"
                    await close(websocket, reason)
                    break
                checked_at = tick
            raw = frame.get("text")
            if raw is None:
                await close(websocket, "invalid_signal")
                break
            while received and received[0] <= tick - 1:
                received.popleft()
            if len(raw.encode("utf-8")) > MAX_SIGNAL_BYTES or len(received) >= MAX_SIGNALS_PER_SECOND:
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
            async with state.lock:
                if state.peers.get(user.role) is not websocket:
                    break
                peers = [peer for role, peer in state.peers.items() if role != user.role]
            for peer in peers:
                await send(peer, raw)
            if message["type"] == "bye":
                await websocket.close(code=1000)
                break
    except (WebSocketDisconnect, RuntimeError, OSError):
        pass
    finally:
        if joined:
            async with state.lock:
                peers = []
                if state.peers.get(user.role) is websocket:
                    del state.peers[user.role]
                    peers = list(state.peers.values())
            for peer in peers:
                await send(peer, {"type": "peer_left"})
        state.users -= 1
        if not state.users:
            _rooms.pop(booking_id, None)
        if joined:
            await anyio.to_thread.run_sync(backend.video_consult.record, user, booking_id, "video_left")
