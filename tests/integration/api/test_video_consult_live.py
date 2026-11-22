"""[TEST] 실제 handshake·접속 로그와 느린 수신자의 방 격리를 확인해요."""

import asyncio
import base64
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect


@pytest.fixture
def live_server(tmp_path):
    root = Path(__file__).resolve().parents[3]
    log_path = tmp_path / "uvicorn.log"
    env = {**os.environ, "DATA_BACKEND": "mock", "FEATURE_VIDEO_CONSULT": "true",
           "PYTHONPATH": str(root / "apps/api"), "MEDIA_DIR": str(tmp_path / "media")}
    launch = """
from datetime import datetime
from app.mock import seed
from app.core import video_consult
seed.video_now = lambda: datetime.fromisoformat('2026-11-22T12:00:00+09:00')
video_consult.now = seed.video_now
from dataclasses import replace
from app.main import app
from app.mock import store
store.reset()
state = store.state()
request = replace(state.requests[seed.VIDEO_REQUEST], id=seed.demo_id('903'), requester_id=seed.PARENT_OTHER)
state.requests[request.id] = request
state.bookings[seed.demo_id('902')] = replace(state.bookings[seed.VIDEO_BOOKING],
    id=seed.demo_id('902'), request_id=request.id, teacher_id=seed.TEACHER_OTHER)
import logging, socket, time
import uvicorn
from uvicorn.protocols.websockets.websockets_sansio_impl import WebSocketsSansIOProtocol
class SmallBufferProtocol(WebSocketsSansIOProtocol):
    def connection_made(self, transport):
        transport.get_extra_info('socket').setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8192)
        super().connection_made(transport)
    def pause_writing(self):
        logging.getLogger('uvicorn.error').info('write buffer paused at %.6f', time.monotonic())
        super().pause_writing()
from uvicorn.config import LOGGING_CONFIG
for formatter in LOGGING_CONFIG['formatters'].values():
    formatter['fmt'] = '[TEST] ' + formatter['fmt']
uvicorn.run(app, fd=int(__import__('sys').argv[1]), ws=SmallBufferProtocol, log_config=LOGGING_CONFIG)
"""
    with socket.socket() as listener, log_path.open("w") as output:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        process = subprocess.Popen([sys.executable, "-c", launch, str(listener.fileno())], cwd=root,
                                   env=env, pass_fds=(listener.fileno(),), stdout=output, stderr=output)
        tickets = ["[TEST]-broken-ticket"]
        try:
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=0.3) as http:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        if http.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    assert process.poll() is None and time.monotonic() < deadline, "[TEST] uvicorn 준비 실패"
                    time.sleep(0.05)
                yield http, f"ws://127.0.0.1:{port}", tickets, log_path
        finally:
            process.terminate()  # 방금 만든 서버 PID에만 종료 신호를 보내요.
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    log = log_path.read_text()
    assert "Logging error" not in log and "Traceback" not in log
    assert all(ticket not in log for ticket in tickets)
    assert process.returncode is not None


def test_uvicorn_rejections_replay_and_ticket_redaction(live_server):
    http, base, tickets, log_path = live_server
    response = http.post("/api/v1/auth/login", json={"login_id": "teacher01", "password": "demo1234"})
    assert response.status_code == 200
    result = http.get("/api/v1/consultations/00000000-0000-4000-8000-000000000901/room",
                      headers={"Authorization": "Bearer " + response.json()["access_token"]})
    assert result.status_code == 200
    room = result.json()
    tickets.append(room["ticket"])
    def denied(path, ticket):
        with connect(base + path + "?ticket=" + ticket, open_timeout=2, close_timeout=2) as ws:
            try:
                ws.recv(timeout=2)
            except ConnectionClosed as error:
                assert error.rcvd.code == 1008 and error.rcvd.reason == "access_denied"
            else:
                raise AssertionError("[TEST] 연결이 닫히지 않았어요")
    assert http.get("/health", params={"ticket": tickets[0]}).status_code == 200
    denied(room["signal_path"], tickets[0])
    denied(f"/api/v1/consultations/{uuid4()}/signal", room["ticket"])
    # 다른 예약 거부와 별개로, 새 접속권의 두 번째 사용도 거부해요.
    room = http.get(result.request.url, headers=result.request.headers).json()
    tickets.append(room["ticket"])
    with connect(base + room["signal_path"] + "?ticket=" + room["ticket"], close_timeout=2) as original:
        denied(room["signal_path"], room["ticket"])
        original.send(json.dumps({"type": "bye", "data": None}))
        try:
            original.recv(timeout=2)
        except ConnectionClosed as error:
            assert error.rcvd.code == 1000
    assert "ticket=[redacted]" in log_path.read_text()


def test_uvicorn_nonreading_peer_leaves_within_three_seconds(live_server):
    http, base, tickets, log_path = live_server

    def room(login, suffix="901"):
        auth = http.post("/api/v1/auth/login", json={"login_id": login, "password": "demo1234"})
        response = http.get(f"/api/v1/consultations/00000000-0000-4000-8000-000000000{suffix}/room",
                            headers={"Authorization": "Bearer " + auth.json()["access_token"]})
        assert response.status_code == 200
        result = response.json()
        tickets.append(result["ticket"])
        return result

    def url(result):
        return base + result["signal_path"] + "?ticket=" + result["ticket"]

    slow = room("parent01")
    port = http.base_url.port
    # 원시 소켓은 handshake까지만 읽어요. 라이브러리의 수신 스레드도 없어요.
    with socket.socket() as raw:
        raw.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 2048)
        raw.settimeout(2)
        raw.connect(("127.0.0.1", port))
        key = base64.b64encode(os.urandom(16)).decode()
        path = slow["signal_path"] + "?ticket=" + slow["ticket"]
        request = (f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{port}\r\nUpgrade: websocket\r\n"
                   f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        raw.sendall(request.encode())
        header = bytearray()
        while not header.endswith(b"\r\n\r\n"):
            chunk = raw.recv(1)
            assert chunk
            header.extend(chunk)
        assert header.startswith(b"HTTP/1.1 101")
        with (connect(url(room("teacher01")), close_timeout=1) as sender,
              connect(url(room("teacher02", "902")), close_timeout=1) as c,
              connect(url(room("parent02", "902")), close_timeout=1) as d):
            assert json.loads(sender.recv(timeout=1)) == {"type": "peer_joined"}
            assert json.loads(c.recv(timeout=1)) == json.loads(d.recv(timeout=1)) == {"type": "peer_joined"}
            payload = json.dumps({"type": "ice", "data": "[TEST]" + "x" * 60000})
            deadline = time.monotonic() + 12
            paused = None
            while time.monotonic() < deadline:
                if paused is None:
                    sender.send(payload)
                time.sleep(0.07)  # 초당 20개 제한 안이에요.
                if paused is None:
                    lines = [line for line in log_path.read_text().splitlines() if "write buffer paused at " in line]
                    if lines:
                        paused = float(lines[0].rsplit(" ", 1)[1])
                        sender.send(payload)  # 가득 찬 버퍼에서 실제 보내기 한 건이 기다려요.
                        started = time.monotonic()
                        c.send(json.dumps({"type": "offer", "data": "[TEST] other room"}))
                        assert json.loads(d.recv(timeout=1))["data"] == "[TEST] other room"
                        other_room_seconds = time.monotonic() - started
                        assert other_room_seconds < 1
                try:
                    event = json.loads(sender.recv(timeout=0.01))
                except TimeoutError:
                    continue
                assert event == {"type": "peer_left"}
                assert paused is not None and time.monotonic() - paused < 3
                (log_path.parent / "timings.json").write_text(json.dumps({
                    "peer_left_seconds": time.monotonic() - paused,
                    "other_room_seconds": other_room_seconds,
                }))
                break
            else:
                raise AssertionError("[TEST] 느린 연결이 3초 안에 peer_left를 보내지 않았어요")
            # 제거 뒤에도 다른 방과 새 접속은 계속 동작해요.
            c.send(json.dumps({"type": "answer", "data": "[TEST] after removal"}))
            assert json.loads(d.recv(timeout=1))["data"] == "[TEST] after removal"
            with connect(url(room("parent01")), close_timeout=1) as replacement:
                assert json.loads(sender.recv(timeout=1)) == {"type": "peer_joined"}
                assert json.loads(replacement.recv(timeout=1)) == {"type": "peer_joined"}


def test_slow_receiver_does_not_block_another_room(monkeypatch):
    from dataclasses import replace
    from datetime import timedelta
    from app import backend
    from app.api.routes import video_consult as route
    from app.core import video_consult as rules

    async def scenario():
        class Socket:
            def __init__(self, token, slow=False):
                self.query_params = {"ticket": token}
                self.incoming, self.outgoing = asyncio.Queue(), asyncio.Queue()
                self.slow, self.blocked = slow, asyncio.Event()

            async def accept(self):
                pass

            async def receive(self):
                return await self.incoming.get()

            async def send_json(self, data):
                await self.outgoing.put(data)

            async def send_text(self, data):
                if self.slow:
                    self.blocked.set()
                    await asyncio.Event().wait()
                await self.outgoing.put(json.loads(data))

            async def close(self, code, reason):
                await self.outgoing.put({"code": code, "reason": reason})
                await self.incoming.put({"type": "websocket.disconnect"})

        ids = [uuid4(), uuid4()]
        monkeypatch.setattr(rules, "settings", replace(rules.settings, feature_video_consult=True))
        monkeypatch.setattr(rules, "ticket_user", lambda token, booking: (SimpleNamespace(role=token[0]), {}))
        monkeypatch.setattr(backend.video_consult, "access", lambda *args: {"closes_at": rules.now() + timedelta(hours=1)})
        def record(*args):
            assert all(not room.lock.locked() for room in route._rooms.values())
        monkeypatch.setattr(backend.video_consult, "record", record)
        a, b, c, d = Socket("teacher1"), Socket("parent1", slow=True), Socket("teacher2"), Socket("parent2")
        tasks = [asyncio.create_task(route.signal(ws, str(booking)))
                 for ws, booking in ((a, ids[0]), (b, ids[0]), (c, ids[1]), (d, ids[1]))]
        try:
            for ws in (a, b, c, d):
                assert await asyncio.wait_for(ws.outgoing.get(), 1) == {"type": "peer_joined"}
            frame = {"type": "websocket.receive", "text": '{"type":"offer","data":"[TEST] signal"}'}
            await a.incoming.put(frame)
            await asyncio.wait_for(b.blocked.wait(), 1)
            await c.incoming.put(frame)
            assert await asyncio.wait_for(d.outgoing.get(), 1) == json.loads(frame["text"])
            assert await asyncio.wait_for(a.outgoing.get(), 3) == {"type": "peer_left"}
            await asyncio.wait_for(tasks[1], 1)
            assert b not in route._rooms[ids[0]].peers.values()
        finally:
            for ws in (a, b, c, d):
                await ws.incoming.put({"type": "websocket.disconnect"})
            await asyncio.wait_for(asyncio.gather(*tasks), 3)
        assert route._rooms == {}
    asyncio.run(scenario())
