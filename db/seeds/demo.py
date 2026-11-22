"""가상 원·계정·반·아이·상담실과 알림장용 식단·보호자 요청 22개.

저장소 루트에서 PYTHONPATH=apps/api python -m db.seeds.demo 로 실행한다.
모의 seed의 고정 ID를 함께 쓰고, 이미 있는 행은 덮어쓰지 않는다.
출처 PR #262 roster_c4.json(가상): 별빛반 18명도 app.mock.seed에서 함께 읽는다.
출처 PR #269 guardian_requests.json(가상): 20개 요청·16명 보호자도 같은 시드를 쓴다.
"""

import argparse
from datetime import datetime, timedelta
import logging

from argon2 import PasswordHasher
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.db import transaction
from app.core.schedule import KST
from app.mock import seed


def seed_demo(connection, *, refresh_note_requests=False):
    connection.execute(text("""
        INSERT INTO organizations (id, name, is_virtual)
        VALUES (:id, '가상 햇살유치원', true) ON CONFLICT DO NOTHING
    """), {"id": seed.ORG})
    for classroom, age in zip(seed.CLASSROOMS, (4, 5), strict=True):
        connection.execute(text("""
            INSERT INTO classrooms (id, org_id, name, age_group, school_year)
            VALUES (:id, :org_id, :name, :age, 2026) ON CONFLICT DO NOTHING
        """), {**classroom, "org_id": seed.ORG, "age": age})
    password_hash = PasswordHasher().hash(seed.DEMO_PASSWORD)
    for user in seed.USERS:
        connection.execute(text("""
            INSERT INTO users (id, org_id, role, login_id, display_name, password_hash)
            VALUES (:id, :org_id, :role, :login_id, :display_name, :password_hash)
            ON CONFLICT DO NOTHING
        """), {**user, "org_id": seed.ORG, "password_hash": password_hash})
    for assignment in seed.CLASSROOM_STAFF:
        connection.execute(text("""
            INSERT INTO classroom_staff (classroom_id, org_id, user_id, valid_from, valid_to)
            VALUES (:classroom_id, :org_id, :user_id, :valid_from, :valid_to) ON CONFLICT DO NOTHING
        """), {**assignment, "org_id": seed.ORG})
    has_feed = connection.scalar(text("SELECT to_regclass('public.feed_posts') IS NOT NULL"))
    for child in seed.CHILDREN:
        # 옛 revision의 왕복 시험에서도 시드를 쓸 수 있게 새 칸은 0010부터 넣어요.
        columns = ", photo_scope" if has_feed else ""
        values = ", :photo_scope" if has_feed else ""
        connection.execute(text(f"""
            INSERT INTO children (id, org_id, classroom_id, display_name, is_virtual{columns})
            VALUES (:id, :org_id, :classroom_id, :display_name, true{values}) ON CONFLICT DO NOTHING
        """), {**child, "org_id": seed.ORG, "photo_scope": seed.PHOTO_SCOPES.get(child["id"], "family")})
        for guardian in child["guardian_ids"]:
            connection.execute(text("""
                INSERT INTO child_guardians (child_id, org_id, user_id, relation)
                VALUES (:child_id, :org_id, :user_id, :relation) ON CONFLICT DO NOTHING
            """), {"child_id": child["id"], "org_id": seed.ORG, "user_id": guardian,
                   "relation": seed.GUARDIAN_RELATIONS.get((child["id"], guardian), "other")})
    for room in seed.ROOMS:
        connection.execute(text("""
            INSERT INTO rooms (id, org_id, name) VALUES (:id, :org_id, :name) ON CONFLICT DO NOTHING
        """), {**room, "org_id": seed.ORG})
    for document_id, title, kind, status, content in seed.DEMO_DOCUMENTS:
        connection.execute(text("""
            INSERT INTO documents (id,org_id,title,doc_type,source,status,ingest_status,content_sha256)
            VALUES (:id,:org,:title,:kind,'virtual',:status,'succeeded',:sha) ON CONFLICT DO NOTHING
        """), {"id": document_id, "org": seed.ORG, "title": title, "kind": kind,
               "status": status, "sha": f"demo:{document_id}"})
        connection.execute(text("""
            INSERT INTO document_chunks (document_id,org_id,chunk_index,content)
            VALUES (:id,:org,0,:content) ON CONFLICT DO NOTHING
        """), {"id": document_id, "org": seed.ORG, "content": content})
    for request in seed.DEMO_NOTE_REQUESTS:
        connection.execute(text("""
            INSERT INTO requests (id,org_id,classroom_id,child_id,requester_id,client_request_id,type,title,body,created_at)
            VALUES (:id,:org,:class,:child_id,:requester_id,:key,:type,:body,:body,:now)
            ON CONFLICT (id) DO UPDATE SET title=coalesce(requests.title, EXCLUDED.title)
        """), {**request, "org": seed.ORG, "class": seed.CLASS_STAR, "key": f"demo:{request['id']}",
               "now": request.get("created_at", datetime.now(KST))})
        # 이전 데모 DB에도 첫 보호자 메시지를 한 번만 채워요. 이미 있는 대화는 덮어쓰지 않아요.
        connection.execute(text("""
            INSERT INTO request_messages (request_id,org_id,sender_type,sender_id,body,created_at)
            SELECT r.id,r.org_id,'user',r.requester_id,r.body,r.created_at FROM requests r
            WHERE r.id=:id AND r.org_id=:org AND NOT EXISTS (
                SELECT 1 FROM request_messages m WHERE (m.request_id,m.org_id)=(r.id,r.org_id)
                  AND m.sender_type='user' AND m.sender_id=r.requester_id)
        """), {"id": request["id"], "org": seed.ORG})
    if refresh_note_requests:
        now = datetime.now(KST)
        latest = max(r["created_at"].astimezone(KST).date() for r in seed.DEMO_NOTE_REQUESTS if "created_at" in r)
        shift = now.date() - latest
        # 고정 fixture 날짜 사이 간격·시각은 유지하고, 날짜 없는 두 예시는 현재 시각을 쓴다.
        refreshed = [{"org": seed.ORG, "id": r["id"],
                      "now": r["created_at"].astimezone(KST) + shift if "created_at" in r else now}
                     for r in seed.DEMO_NOTE_REQUESTS]
        # 명시한 날짜 갱신은 최초 보호자 메시지도 맞춰요. 재실행해도 같은 행만 고쳐요.
        connection.execute(text("""
            UPDATE request_messages SET created_at=:now WHERE id=(
                SELECT m.id FROM request_messages m JOIN requests r
                  ON (r.id,r.org_id)=(m.request_id,m.org_id)
                WHERE r.id=:id AND r.org_id=:org AND m.sender_type='user' AND m.sender_id=r.requester_id
                ORDER BY m.id LIMIT 1)
        """), refreshed)
        connection.execute(text("""
            UPDATE requests SET created_at=:now
            WHERE org_id=:org AND id=:id
        """), refreshed)

    if has_feed:
        seed_feed(connection)
    from app.core.config import settings
    if settings.feature_video_consult or settings.feature_voice_analysis:
        seed_video_consult(connection)


def seed_video_consult(connection, now=None):
    now = now if now is not None else seed.video_now()
    booking = connection.execute(text("""
        SELECT *, upper(period) AS end FROM consultation_bookings WHERE id=:id AND org_id=:org FOR UPDATE
    """), {"id": seed.VIDEO_BOOKING, "org": seed.ORG}).mappings().one_or_none()
    if booking:
        if (booking["status"] == "confirmed"
                and (booking["expected_end_at"] or booking["end"]) + timedelta(minutes=30) < now):
            period = seed.video_period(now=now)
            if period is None:
                return
            try:
                # EXCLUDE가 마지막 충돌 판정을 맡고, 실패해도 바깥 시드는 계속해요.
                with connection.begin_nested():
                    connection.execute(text("""
                        UPDATE consultation_bookings SET period=tstzrange(:start,:end,'[)'), expected_end_at=NULL
                        WHERE id=:id
                    """), {"id": seed.VIDEO_BOOKING, **period})
            except IntegrityError as error:
                if error.orig.sqlstate != "23P01":
                    raise
                logging.getLogger(__name__).warning("가상 화상상담 예약 갱신 생략: 담임·상담실 시간 겹침")
        return

    if connection.scalar(text("SELECT EXISTS (SELECT 1 FROM consultation_bookings WHERE org_id=:org AND status='confirmed')"),
                         {"org": seed.ORG}):
        return
    period = seed.video_period(now=now)
    if period is None:
        return
    from app.modules.requests.events import record
    connection.execute(text("""
        INSERT INTO requests(id,org_id,classroom_id,child_id,requester_id,client_request_id,type,body,status)
        VALUES (:id,:org,:class,:child,:parent,'demo-video-consult','consultation','가상 화상상담','sent_or_booked')
        ON CONFLICT DO NOTHING
    """), {"id": seed.VIDEO_REQUEST, "org": seed.ORG, "class": seed.CLASS_STAR,
           "child": seed.CHILD, "parent": seed.PARENT})
    inserted = connection.scalar(text("""
        INSERT INTO consultation_bookings(id,org_id,request_id,teacher_id,room_id,period,confirmed_by)
        VALUES (:id,:org,:req,:teacher,:room,tstzrange(:start,:end,'[)'),:teacher)
        ON CONFLICT DO NOTHING RETURNING id
    """), {"id": seed.VIDEO_BOOKING, "org": seed.ORG, "req": seed.VIDEO_REQUEST, "teacher": seed.TEACHER,
           "room": seed.ROOM, **period})
    if inserted:
        req = connection.execute(text("SELECT * FROM requests WHERE id=:id"), {"id": seed.VIDEO_REQUEST}).mappings().one()
        record(connection, req, "booked", actor_type="user", actor_id=seed.TEACHER)


def seed_feed(connection):
    from app.core import media

    first_posts = False
    for post in seed.FEED_POSTS:
        inserted = connection.scalar(text("""
            INSERT INTO feed_posts(id,org_id,lane,classroom_id,author_id,body,created_at)
            VALUES (:id,:org,:lane,:classroom_id,:author_id,:body,:now) ON CONFLICT DO NOTHING RETURNING id
        """), {**post, "org": seed.ORG, "now": seed.FEED_CREATED_AT})
        first_posts = first_posts or inserted is not None
    if first_posts:
        # 0009 시드→0010에서도 새 DB와 같게, 이후 가족이 바꾼 값은 보존해요.
        for child_id, scope in seed.PHOTO_SCOPES.items():
            connection.execute(text("UPDATE children SET photo_scope=:scope WHERE id=:id AND org_id=:org"),
                               {"id": child_id, "org": seed.ORG, "scope": scope})
    png = seed.feed_png()
    metadata = media.inspect(png)
    for photo_id, post_id, tags in seed.FEED_PHOTOS:
        # 작성자가 지운 시드 글은 기동 때도 복원하지 않아요.
        inserted = connection.scalar(text("""
            INSERT INTO feed_photos(id,org_id,post_id,storage_path,media_type,size_bytes,sha256,created_at)
            SELECT :id,:org,:post,:path,:media_type,:size_bytes,:sha256,:now
            FROM feed_posts WHERE id=:post AND org_id=:org AND deleted_at IS NULL
            ON CONFLICT DO NOTHING RETURNING id
        """), {**metadata, "id": photo_id, "org": seed.ORG, "post": post_id, "path": f"{photo_id}.png",
               "now": seed.FEED_CREATED_AT})
        if inserted:
            for child_id in tags:
                connection.execute(text("""
                    INSERT INTO feed_photo_children(org_id,photo_id,child_id) VALUES (:org,:photo,:child)
                """), {"org": seed.ORG, "photo": photo_id, "child": child_id})
        active = connection.scalar(text("""
            SELECT p.storage_path FROM feed_photos p JOIN feed_posts f ON (f.id,f.org_id)=(p.post_id,p.org_id)
            WHERE p.id=:id AND p.org_id=:org AND f.deleted_at IS NULL AND p.sha256=:sha256
        """), {"id": photo_id, "org": seed.ORG, "sha256": metadata["sha256"]})
        if active and not media.path(active).is_file():
            media.save(png, metadata, file_id=photo_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="가상 원 데모 시드")
    parser.add_argument("--refresh-note-requests", action="store_true",
                        help="가상 요청의 날짜 간격을 유지하며 가장 늦은 fixture 날짜를 오늘로 옮겨요")
    args = parser.parse_args()
    with transaction() as connection:
        seed_demo(connection, refresh_note_requests=args.refresh_note_requests)
    print(f"가상 원 시드 완료: 계정 {len(seed.USERS)}개, 비밀번호 demo1234 (이미 있는 행은 유지)")
