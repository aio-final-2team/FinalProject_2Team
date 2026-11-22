"""[TEST] 실제 handshake·접속 로그와 느린 수신자의 방 격리를 확인해요."""

import asyncio
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
from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect


def test_uvicorn_rejections_replay_and_ticket_redaction(tmp_path):
    root = Path(__file__).resolve().parents[3]
    log_path = tmp_path / "uvicorn.log"
    env = {**os.environ, "DATA_BACKEND": "mock", "FEATURE_VIDEO_CONSULT": "true",
           "PYTHONPATH": str(root / "apps/api"), "MEDIA_DIR": str(tmp_path / "media")}
    launch = """
import uvicorn
from uvicorn.config import LOGGING_CONFIG
for formatter in LOGGING_CONFIG['formatters'].values():
    formatter['fmt'] = '[TEST] ' + formatter['fmt']
uvicorn.run('app.main:app', fd=int(__import__('sys').argv[1]), log_config=LOGGING_CONFIG)
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
                response = http.post("/api/v1/auth/login", json={"login_id": "teacher01", "password": "demo1234"})
                assert response.status_code == 200
                result = http.get("/api/v1/consultations/00000000-0000-4000-8000-000000000901/room",
                                  headers={"Authorization": "Bearer " + response.json()["access_token"]})
                assert result.status_code == 200
                room = result.json()
                tickets.append(room["ticket"])
                base = f"ws://127.0.0.1:{port}"
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
        finally:
            process.terminate()  # 방금 만든 서버 PID에만 종료 신호를 보내요.
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
    log = log_path.read_text()
    assert "Logging error" not in log
    assert "ticket=[redacted]" in log
    assert all(ticket not in log for ticket in tickets)
    assert process.returncode is not None


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
            assert await asyncio.wait_for(b.outgoing.get(), 3) == {"code": 1008, "reason": "slow_peer"}
            assert await asyncio.wait_for(a.outgoing.get(), 1) == {"type": "peer_left"}
        finally:
            for ws in (a, b, c, d):
                await ws.incoming.put({"type": "websocket.disconnect"})
            await asyncio.wait_for(asyncio.gather(*tasks), 3)
        assert route._rooms == {}
    asyncio.run(scenario())
