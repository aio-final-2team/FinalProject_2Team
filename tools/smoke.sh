#!/usr/bin/env bash
set -Eeuo pipefail
exec > >(sed -u 's/^/[TEST] /') 2>&1
if (( $# != 1 )); then
    echo "사용법: $0 <API 기준 URL>"
    exit 2
fi

# Python 표준 라이브러리만 써요. 토큰·비밀번호·응답 본문은 출력하지 않아요.
python3 - "$1" <<'PY'
import json
import os
import sys
import time
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo


def main():
    base = sys.argv[1].rstrip("/")
    parts = urlsplit(base)
    if (parts.scheme not in ("http", "https") or not parts.netloc or parts.query or parts.fragment
            or parts.username is not None):
        raise ValueError("http(s) 기준 URL을 넣어 주세요. 인증 정보·쿼리·fragment는 받지 않아요.")
    timeout = float(os.getenv("SMOKE_TIMEOUT", "180"))
    if not 0 < timeout <= 3600:
        raise ValueError("SMOKE_TIMEOUT은 0보다 크고 3600 이하인 초예요.")
    token = None

    def call(path, body=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(base + path, headers=headers,
                          data=None if body is None else json.dumps(body).encode())
        try:
            with urlopen(request, timeout=10) as response:
                return json.load(response)
        except HTTPError as error:
            raise RuntimeError(f"{request.get_method()} {path.split('?')[0]}: HTTP {error.code}") from None

    deadline = time.monotonic() + timeout
    while True:
        try:
            if call("/health").get("status") != "ok":
                raise RuntimeError("health 응답이 ok가 아니에요.")
            break
        except (OSError, RuntimeError):
            if time.monotonic() >= deadline:
                raise RuntimeError("health 준비 시간 초과") from None
            time.sleep(1)
    print("health 통과", flush=True)
    login = call("/api/v1/auth/login", {
        "login_id": os.getenv("SMOKE_LOGIN_ID", "teacher01"),
        "password": os.getenv("SMOKE_PASSWORD", "demo1234"),
    })
    token = login["access_token"]
    classroom = login["user"]["classroom_ids"][0]
    print("담임 로그인 통과", flush=True)
    children = call(f"/api/v1/classrooms/{classroom}/children")["items"]
    if not children or any(child["classroom_id"] != classroom for child in children):
        raise RuntimeError("담임 반의 아이 목록이 비었거나 다른 반 아이가 있어요.")
    print(f"반 아이 목록 {len(children)}명 통과", flush=True)
    note_date = os.getenv("SMOKE_NOTE_DATE") or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    draft = call("/api/v1/daily-notes/drafts", {
        "classroom_id": classroom, "note_date": note_date,
        "activities": "[TEST] 블록 놀이", "supplies": "[TEST] 물통",
        "child_memos": [{"child_id": children[0]["id"], "memo": "[TEST] 친구와 블록을 쌓았어요"}],
    })
    deadline = time.monotonic() + timeout
    while True:
        state = call("/api/v1/daily-notes/drafts/" + draft["input_id"])
        status = state["draft_status"]
        if status == "succeeded":
            break
        if status not in ("queued", "running"):
            raise RuntimeError(f"초안 작업 실패: {status}")
        if time.monotonic() >= deadline:
            raise RuntimeError("초안 작업 시간 초과")
        time.sleep(1)
    print("초안 생성·상태 succeeded 통과", flush=True)
    child_ids = set()
    page = 1
    while True:
        notes = call("/api/v1/daily-notes?" + urlencode({
            "classroom_id": classroom, "date": note_date, "page": page, "size": 100,
        }))
        for note in notes["items"]:
            if note["note_date"] != note_date or not note["content"]["items"]:
                raise RuntimeError("알림장의 날짜나 본문이 맞지 않아요.")
            child_ids.add(note["child_id"])
        if page * 100 >= notes["total"]:
            break
        page += 1
    if child_ids != {child["id"] for child in children}:
        raise RuntimeError("반 아이 목록과 초안 목록의 아이가 달라요.")
    print(f"알림장 목록 {len(child_ids)}개 통과 · smoke 성공", flush=True)


try:
    main()
except (OSError, URLError, ValueError, KeyError, IndexError, TypeError, RuntimeError) as error:
    print(f"smoke 실패: {error}", file=sys.stderr)
    sys.exit(1)
PY
