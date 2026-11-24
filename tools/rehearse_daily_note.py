"""알림장 시연 리허설: 시연 기준 데이터로 담임 입력부터 반 발송까지 API를 차례로 부른다.

    PYTHONPATH=. python tools/rehearse_daily_note.py --dry-run          # 부를 순서만 본다(서버에 아무것도 보내지 않음)
    PYTHONPATH=. python tools/rehearse_daily_note.py --base-url http://localhost:8000

기준은 Docs/Step2/알림장_에이전트_흐름.md 10장이다. 별빛반 20명에게 11/20 하루치 반 활동·준비물·메모를 넣고,
날짜는 실행한 날(한국 시각)을 쓴다. 보호자 요청은 미리 `python -m db.seeds.demo --refresh-note-requests`로 오늘로 옮겨 둔다.
지아는 그날 투약 요청이 있어서, 그래프의 코드 검사(code_checks)가 모델 판단과 상관없이 확인 항목을 남긴다.
그래서 지아를 빼고 모두 확인한 뒤 보내면 반 발송이 지아 때문에 한 번 막힌다. 순서와 화면은 Docs/Step2/알림장_시연_리허설.md.
서버에 그날 알림장을 실제로 만들고 보내므로, 시연 당일에는 팀 서버에서 돌리지 않는다.
"""

import argparse
import json
import sys
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

DATA = Path(__file__).resolve().parents[1] / "data/fixtures/kg-demo-01/daily_notes"
KST = timezone(timedelta(hours=9))
API = "/api/v1"
SOURCE_DAY = "2026-11-20"
EDIT_CHILD, BLOCKED_CHILD = "하늘", "지아"
EDITED_LINE = "기침을 가끔 했지만 열은 없었고 낮잠도 잘 잤어요."
STATUSES = ("draft", "needs_check", "ready", "sent")
PLAN = [
    ("로그인", "POST /auth/login · GET /classrooms/{반}/children", "담임 계정, 반 아이 수"),
    ("초안 만들기", "POST /daily-notes/drafts", "11/20 반 활동·준비물·메모(빈 메모 제외)를 오늘 날짜로"),
    ("진행 상태", "GET /daily-notes/drafts/{input_id}", "succeeded나 failed가 될 때까지 1초마다"),
    ("아이별 초안", "GET /daily-notes · GET /cards?kind=daily_note", "상태별 수, 확인 항목이 있는 아이, 확인 카드"),
    ("한 아이 고치기·확인", "PATCH /daily-notes/{note_id} 두 번", "하늘: 아이 메모 줄을 고치며 항목 해결 → 확인"),
    ("나머지 확인", "PATCH /daily-notes/{note_id}", "하늘·지아를 뺀 아이: 항목이 있으면 해결하며 확인"),
    ("반 발송 시도", "POST /daily-notes/send", "지아가 확인 전이라 409 NOTE_BATCH_BLOCKED"),
    ("막힌 아이 해결", "PATCH /daily-notes/{note_id} 두 번 · POST /daily-notes/send", "지아: 항목 해결(이때 보내도 409) → 확인"),
    ("반 발송", "POST /daily-notes/send · GET /cards?kind=daily_note&filter=done", "200 sent_count, 카드 done"),
    ("학부모 쪽", "POST /auth/login · GET /daily-notes · GET /notifications", "parent01이 하늘 알림장과 알림을 받음"),
]


class Failed(Exception):
    pass


def demo_input(classroom_id, note_date):
    """class_days·child_memos의 11/20 값을 그대로 쓴다. 화면처럼 빈 메모는 보내지 않는다."""
    day = next(d for d in json.loads((DATA / "class_days.json").read_text("utf-8"))["days"]
               if d["note_date"] == SOURCE_DAY)
    roster = json.loads((DATA / "roster_c4.json").read_text("utf-8"))
    ids = {c["child_key"]: c["child_id"] for c in roster["children"] + roster["seed_children"]}
    memos = [{"child_id": ids[m["child_key"]], "memo": m["memo"]}
             for m in json.loads((DATA / "child_memos.json").read_text("utf-8"))["memos"]
             if m["note_date"] == SOURCE_DAY and m["memo"].strip()]
    return {"classroom_id": classroom_id, "note_date": note_date, "activities": day["activities"],
            "supplies": day["supplies"], "child_memos": memos}


def rehearse(client, login_id, password, note_date, parent_login="parent01", wait=330.0, out=print):
    """단계마다 한 줄을 out으로 찍고, 시험이 볼 수 있게 장면 요약을 돌려준다. ID·시각은 찍지 않는다."""
    def call(method, path, expect, token, **kwargs):
        response = client.request(method, API + path, headers={"Authorization": f"Bearer {token}"} if token else {},
                                  **kwargs)
        if response.status_code not in expect:
            raise Failed(f"{method} {path} → {response.status_code}: {response.text[:300]}")
        return response.json()

    def say(step, text):
        out(f"[{step}] {PLAN[step - 1][0]} — {text}")

    def checks(rows):
        return {names[n["child_id"]]: sorted(c["kind"] for c in n["open_checks"]) for n in rows if n["open_checks"]}

    def patch(note, **body):
        return call("PATCH", f"/daily-notes/{note['id']}", (200,), token, json=body)["note"]

    def card(done=False):
        rows = call("GET", "/cards", (200,), token, params={"kind": "daily_note", **({"filter": "done"} if done else {})})
        return ", ".join(sorted(c["status"] for c in rows["items"])) or "없음"

    login = call("POST", "/auth/login", (200,), None, json={"login_id": login_id, "password": password})
    token, classroom = login["access_token"], login["user"]["classroom_ids"][0]
    names = {c["id"]: c["display_name"] for c in call("GET", f"/classrooms/{classroom}/children", (200,), token)["items"]}
    say(1, f"{login['user']['display_name']}, 반 아이 {len(names)}명")

    body = demo_input(classroom, note_date)
    response = client.post(API + "/daily-notes/drafts", json=body, headers={"Authorization": f"Bearer {token}"})
    if response.status_code == 200:
        raise Failed("이 반·날짜의 작업이 이미 있어요. 리허설은 알림장이 없는 날짜에서 시작해요(새 DB나 다음 날).")
    if response.status_code != 202:
        raise Failed(f"POST /daily-notes/drafts → {response.status_code}: {response.text[:300]}")
    job = response.json()
    say(2, f"202, draft_status={job['draft_status']}, 메모 {len(body['child_memos'])}명")

    started = time.monotonic()
    while job["draft_status"] in ("queued", "running"):
        if time.monotonic() - started > wait:
            raise Failed(f"{wait:.0f}초 안에 초안 작업이 끝나지 않았어요(draft_status={job['draft_status']}).")
        time.sleep(1)
        job = call("GET", f"/daily-notes/drafts/{job['input_id']}", (200,), token)
    say(3, f"draft_status={job['draft_status']}")
    out(f"    (걸린 시간 {time.monotonic() - started:.0f}초)")
    if job["draft_status"] != "succeeded":
        raise Failed(f"초안 작업이 실패했어요: {job['error']}")

    notes = call("GET", "/daily-notes", (200,), token,
                 params={"classroom_id": classroom, "date": note_date, "size": 100, "sort": "created_at"})["items"]
    by_name = {names[n["child_id"]]: n for n in notes}
    flagged = checks(notes)
    counts = Counter(n["status"] for n in notes)
    say(4, f"{len(notes)}명 ({', '.join(f'{s} {counts[s]}' for s in STATUSES if counts[s])}), "
           f"확인 항목: {flagged}, 확인 카드 {card()}")
    if BLOCKED_CHILD not in flagged:
        raise Failed(f"{BLOCKED_CHILD}에게 확인 항목이 없어 발송 막힘 장면을 만들 수 없어요.")

    note = by_name[EDIT_CHILD]
    lines = [line for line in note["content"]["items"] if line["key"] != "child"]
    lines.insert(1, {"key": "child", "label": "아이 메모", "value": EDITED_LINE, "source": {"type": "teacher_input"}})
    edited = patch(note, content={"items": lines}, resolved_checks=[c["id"] for c in note["open_checks"]])
    say(5, f"{EDIT_CHILD} {note['status']} → {edited['status']} → {patch(note, confirm=True)['status']}")

    resolved = []
    for name, note in by_name.items():
        if name not in (EDIT_CHILD, BLOCKED_CHILD):
            patch(note, resolved_checks=[c["id"] for c in note["open_checks"]], confirm=True)
            resolved += [name] if note["open_checks"] else []
    say(6, f"{len(by_name) - 2}명 ready, 그중 항목을 해결한 아이: {', '.join(resolved) or '없음'}")

    error = call("POST", "/daily-notes/send", (409,), token, json={"classroom_id": classroom, "note_date": note_date})
    blocked = {names[n["child_id"]]: sorted(c["kind"] for c in n["open_checks"])
               for n in error["error"]["details"]["blocked"]}
    say(7, f"409 {error['error']['code']}, 막힌 아이: {blocked}")
    if list(blocked) != [BLOCKED_CHILD]:
        raise Failed(f"{BLOCKED_CHILD} 한 명만 막혀야 하는데 {blocked}예요.")

    note = by_name[BLOCKED_CHILD]
    checked = patch(note, resolved_checks=[c["id"] for c in note["open_checks"]])
    still = call("POST", "/daily-notes/send", (409,), token,
                 json={"classroom_id": classroom, "note_date": note_date})["error"]["details"]["blocked"]
    if [(names[n["child_id"]], n["open_checks"]) for n in still] != [(BLOCKED_CHILD, [])]:
        raise Failed(f"확인 전 {BLOCKED_CHILD}만 막혀야 하는데 {still}예요.")
    say(8, f"{BLOCKED_CHILD} {note['status']} → {checked['status']}(이때 보내도 409, 남은 항목 0개) → "
           f"{patch(note, confirm=True)['status']}")

    sent = call("POST", "/daily-notes/send", (200,), token, json={"classroom_id": classroom, "note_date": note_date})
    say(9, f"200, sent_count={sent['sent_count']}, 확인 카드 {card(done=True)}")

    parent = call("POST", "/auth/login", (200,), None, json={"login_id": parent_login, "password": password})
    seen = call("GET", "/daily-notes", (200,), parent["access_token"], params={"date": note_date})["items"]
    alerts = call("GET", "/notifications", (200,), parent["access_token"])["items"]
    child_lines = [line["value"] for n in seen for line in n["content"]["items"] if line["key"] == "child"]
    say(10, f"{parent['user']['display_name']}: 알림장 {[(names[n['child_id']], n['status']) for n in seen]}, "
            f"아이 메모 줄 {child_lines}, 오늘 알림장 알림 {sum(a['kind'] == 'note_sent' for a in alerts)}건")
    return {"flagged": flagged, "blocked": blocked, "sent_count": sent["sent_count"],
            "parent_notes": [(names[n["child_id"]], n["status"]) for n in seen], "parent_child_lines": child_lines}


def main():
    parser = argparse.ArgumentParser(description="알림장 시연 리허설(담임 입력 → 초안 → 확인 → 발송 막힘 → 발송)")
    parser.add_argument("--base-url", default="http://localhost:8000", help="API 주소. 팀 서버는 접속 주소를 넣는다")
    parser.add_argument("--login", default="teacher01")
    parser.add_argument("--password", default="demo1234", help="가상 원 시드 계정 비밀번호")
    parser.add_argument("--parent-login", default="parent01")
    parser.add_argument("--date", default=datetime.now(KST).date().isoformat(), help="기본은 오늘(한국 시각)")
    parser.add_argument("--wait", type=float, default=330, help="초안 작업을 기다릴 최대 초(작성기 제한 300초 + 여유)")
    parser.add_argument("--dry-run", action="store_true", help="서버에 보내지 않고 부를 순서만 보여 준다")
    parser.add_argument("--remote-ok", action="store_true", help="로컬이 아닌 서버에서 그날 알림장을 실제로 보내도 된다")
    args = parser.parse_args()
    host = httpx.URL(args.base_url).host
    if not args.dry_run and host not in ("localhost", "127.0.0.1") and not args.remote_ok:
        print(f"{host}에서 그날 반 알림장을 실제로 만들고 보내요. 시연 당일이 아닌지 확인하고 --remote-ok를 붙여 주세요.",
              file=sys.stderr)
        return 2
    if args.dry_run:
        for step, (name, calls, what) in enumerate(PLAN, start=1):
            print(f"[{step}] {name} — {calls} · {what}")
        return 0
    with httpx.Client(base_url=args.base_url, timeout=30) as client:
        try:
            rehearse(client, args.login, args.password, args.date, args.parent_login, args.wait)
        except Failed as error:
            print(f"리허설 중단: {error}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
