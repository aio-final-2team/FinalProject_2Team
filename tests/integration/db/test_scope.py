"""T24: 실제 관계·기간·재배정과 HTTP 404 뒤에도 남는 권한 거부 이력."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core import scope, users
from app.core.auth import issue_token
from app.core.errors import ApiError
from app.core.schedule import KST
from app.mock import seed


@pytest.fixture
def records(seeded_db):
    ids = {name: uuid4() for name in ("org", "class", "teacher", "parent", "child", "request", "card",
                                     "input", "note", "local_request", "local_card", "local_input", "local_note",
                                     "report")}
    with seeded_db.begin() as connection:
        connection.execute(text("INSERT INTO organizations (id,name) VALUES (:org,'[TEST] 다른 원')"), ids)
        connection.execute(text("""
            INSERT INTO classrooms (id,org_id,name,school_year) VALUES (:class,:org,'[TEST] 다른 반',2026)
        """), ids)
        for role in ("teacher", "parent"):
            connection.execute(text("""
                INSERT INTO users (id,org_id,role,display_name,login_id,password_hash)
                VALUES (:id,:org,:role,'[TEST] 다른 사람',:login_id,'not-used')
            """), {"id": ids[role], "org": ids["org"], "role": role, "login_id": f"other-{role}"})
        connection.execute(text("""
            INSERT INTO children (id,org_id,classroom_id,display_name)
            VALUES (:child,:org,:class,'[TEST] 다른 아이')
        """), ids)
        connection.execute(text("""
            INSERT INTO child_guardians (child_id,org_id,user_id,relation) VALUES (:child,:org,:parent,'other')
        """), ids)
        for local in (False, True):
            values = ({"org": seed.ORG, "class": seed.CLASS_STAR, "parent": seed.PARENT,
                       "teacher": seed.TEACHER, "child": seed.CHILD,
                       **{name: ids[f"local_{name}"] for name in ("request", "card", "input", "note")}}
                      if local else ids)
            connection.execute(text("""
                INSERT INTO requests (id,org_id,classroom_id,child_id,requester_id,client_request_id,type,body)
                VALUES (:request,:org,:class,:child,:parent,'[TEST] scope','complaint','[TEST] 민원')
            """), values)
            connection.execute(text("""
                INSERT INTO cards (id,org_id,request_id,kind,assignee_id)
                VALUES (:card,:org,:request,'reply_draft',:teacher)
            """), values)
            connection.execute(text("""
                INSERT INTO daily_note_inputs (id,org_id,classroom_id,note_date,author_id)
                VALUES (:input,:org,:class,CURRENT_DATE,:teacher)
            """), values)
            connection.execute(text("""
                INSERT INTO daily_notes (id,org_id,input_id,child_id,note_date,status,confirmed_by,confirmed_at,content)
                VALUES (:note,:org,:input,:child,CURRENT_DATE,'sent',:teacher,now(),'{"items": []}')
            """), values)
        connection.execute(text("""
            INSERT INTO cards (id,org_id,request_id,kind,assignee_id)
            VALUES (:report,:org,:request,'director_report',:director)
        """), {"report": ids["report"], "org": seed.ORG, "request": ids["local_request"], "director": seed.DIRECTOR})
    return ids


@pytest.mark.parametrize("resource", ["request", "card", "input", "note"])
@pytest.mark.parametrize("actor", ["other_class", "other_org"])
def test_http_foreign_scope_is_404_and_commits_audit(db_client, records, seeded_db, resource, actor):
    user_id = seed.TEACHER_OTHER if actor == "other_class" else records["teacher"]
    user = users.get_user(user_id)
    paths = {"request": f"/requests/{records['local_request']}", "card": f"/cards/{records['local_card']}",
             "input": f"/daily-notes/drafts/{records['local_input']}", "note": f"/daily-notes/{records['local_note']}"}
    headers = {"Authorization": "Bearer " + issue_token(user), "X-Request-ID": "scope-trace"}
    response = db_client.request("PATCH" if resource == "note" else "GET", "/api/v1" + paths[resource],
                                 headers=headers, **({"json": {}} if resource == "note" else {}))
    assert response.status_code == 404
    assert response.json()["error"] == {"code": "NOT_FOUND", "message": "찾는 자료가 없어요.",
                                         "trace_id": "scope-trace", "details": {}}
    assert response.headers["X-Request-ID"] == "scope-trace"
    # 새 연결에서 읽어 404 예외 뒤에도 커밋됐음을 확인한다.
    with seeded_db.connect() as connection:
        event = connection.execute(text("SELECT * FROM events ORDER BY id DESC LIMIT 1")).mappings().one()
    assert event["action"] == "permission_denied" and event["actor_type"] == "user"
    assert event["actor_id"] == user.id and event["org_id"] == user.org_id
    assert event["detail"]["trace_id"] == "scope-trace"
    if actor == "other_org":
        assert event["request_id"] is None and event["card_id"] is None
    else:
        assert event["request_id"] == (records["local_request"] if resource in ("request", "card") else None)


@pytest.mark.parametrize("resource", ["request", "card", "child", "classroom", "note", "note_input"])
def test_org_filter_runs_before_director_scope(seeded_db, records, resource):
    ids = {"request": "request", "card": "card", "child": "child", "classroom": "class",
           "note": "note", "note_input": "input"}
    with pytest.raises(ApiError) as error:
        getattr(scope, f"{resource}_in_scope")(users.get_user(seed.DIRECTOR), records[ids[resource]])
    assert (error.value.status, error.value.code) == (404, "NOT_FOUND")


@pytest.mark.parametrize("child", [seed.CHILD_OTHER, seed.demo_id("503")])
def test_parent_cannot_access_another_child_even_in_same_class(seeded_db, child):
    with pytest.raises(ApiError) as error:
        scope.child_in_scope(users.get_user(seed.PARENT), child)
    assert error.value.status == 404
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='permission_denied'")) == 1


def test_parent_request_ownership_and_live_guardian_link(db_client, seeded_db, records):
    for parent_id in (seed.PARENT_OTHER, seed.PARENT):
        if parent_id == seed.PARENT:
            with seeded_db.begin() as connection:
                connection.execute(text("DELETE FROM child_guardians WHERE user_id=:id"), {"id": parent_id})
        response = db_client.get(f"/api/v1/requests/{records['local_request']}",
                                 headers={"Authorization": "Bearer " + issue_token(users.get_user(parent_id))})
        assert response.status_code == 404
    assert users.children_of(seed.PARENT) == []


@pytest.mark.parametrize("start,end,allowed", [(None, None, True), (0, 0, True), (-1, 1, True),
                                              (1, None, False), (None, -1, False), (-2, -1, False)])
def test_substitute_assignment_dates_are_inclusive(seeded_db, records, start, end, allowed):
    today = datetime.now(KST).date()
    with seeded_db.begin() as connection:
        connection.execute(text("DELETE FROM classroom_staff WHERE user_id=:id"), {"id": seed.TEACHER_OTHER})
        connection.execute(text("""
            INSERT INTO classroom_staff (org_id,classroom_id,user_id,valid_from,valid_to)
            VALUES (:org,:class,:id,:start,:end)
        """), {"org": seed.ORG, "class": seed.CLASS_STAR, "id": seed.TEACHER_OTHER,
               "start": None if start is None else today + timedelta(days=start),
               "end": None if end is None else today + timedelta(days=end)})
    user = users.get_user(seed.TEACHER_OTHER)
    assert users.classroom_ids_of(user.id) == ([seed.CLASS_STAR] if allowed else [])
    for check, resource_id in ((scope.request_in_scope, records["local_request"]),
                               (scope.card_in_scope, records["local_card"]),
                               (scope.note_input_in_scope, records["local_input"])):
        if allowed:
            assert check(user, resource_id)["id"] == resource_id
        else:
            with pytest.raises(ApiError) as error:
                check(user, resource_id)
            assert error.value.status == 404


def test_reassignment_allows_only_its_card_and_request(seeded_db, records):
    user = users.get_user(seed.TEACHER_OTHER)
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE cards SET assignee_id=:user WHERE id=:card"),
                           {"user": user.id, "card": records["local_card"]})
    assert scope.card_in_scope(user, records["local_card"])["id"] == records["local_card"]
    assert scope.request_in_scope(user, records["local_request"])["id"] == records["local_request"]
    with pytest.raises(ApiError):
        scope.card_in_scope(user, records["report"])
    with pytest.raises(ApiError):
        scope.child_in_scope(user, seed.CHILD)
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE cards SET assignee_id=:user WHERE id=:card"),
                           {"user": seed.TEACHER, "card": records["local_card"]})
    with pytest.raises(ApiError):
        scope.request_in_scope(user, records["local_request"])


@pytest.mark.parametrize("decision", ["approve", "edit_approve", "complete"])
def test_director_cannot_approve_or_complete_complaint(seeded_db, records, decision):
    with pytest.raises(ApiError) as error:
        scope.card_in_scope(users.get_user(seed.DIRECTOR), records["local_card"], decision=decision)
    assert (error.value.status, error.value.code) == (403, "FORBIDDEN_ROLE")


def test_director_report_decision_is_director_only(seeded_db, records):
    with pytest.raises(ApiError) as error:
        scope.card_in_scope(users.get_user(seed.TEACHER), records["report"], decision="hold")
    assert (error.value.status, error.value.code) == (403, "FORBIDDEN_ROLE")
    assert scope.card_in_scope(users.get_user(seed.DIRECTOR), records["report"], decision="hold")["id"] == records["report"]


def test_parent_only_sees_sent_notes_for_own_child(seeded_db, records):
    user = users.get_user(seed.PARENT)
    assert scope.note_in_scope(user, records["local_note"])["id"] == records["local_note"]
    with pytest.raises(ApiError):
        scope.note_in_scope(users.get_user(seed.PARENT_OTHER), records["local_note"])
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE daily_notes SET status='draft' WHERE id=:id"), {"id": records["local_note"]})
    with pytest.raises(ApiError):
        scope.note_in_scope(user, records["local_note"])


@pytest.mark.parametrize("login_id,path", [("parent01", "/cards"), ("teacher01", "/overview"),
                                          ("director01", "/requests")])
def test_wrong_role_is_403_before_pending_workflow(db_client, login_id, path):
    token = db_client.post("/api/v1/auth/login", json={"login_id": login_id, "password": "demo1234"}).json()["access_token"]
    headers = {"Authorization": "Bearer " + token}
    response = (db_client.post("/api/v1" + path, headers=headers, json={}) if path == "/requests"
                else db_client.get("/api/v1" + path, headers=headers))
    assert response.status_code == 403 and response.json()["error"]["code"] == "FORBIDDEN_ROLE"


def test_unimplemented_workflows_never_use_mock(db_client, records):
    user = users.get_user(seed.TEACHER)
    response = db_client.post(f"/api/v1/cards/{records['local_card']}/bookings",
                             headers={"Authorization": "Bearer " + issue_token(user)})
    assert response.status_code == 501 and response.json()["error"]["code"] == "NOT_IMPLEMENTED"


def test_invalid_password_hash_is_401(db_client, seeded_db):
    with seeded_db.begin() as connection:
        connection.execute(text("UPDATE users SET password_hash='invalid' WHERE id=:id"), {"id": seed.TEACHER})
    response = db_client.post("/api/v1/auth/login", json={"login_id": "teacher01", "password": "demo1234"})
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/classrooms/{classroom}/children",
                                   "/daily-notes?date=2026-11-20&classroom_id={classroom}"])
def test_classroom_urls_check_scope(db_client, records, path):
    headers = {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}
    for classroom, status in ((seed.CLASS_STAR, 200), (seed.CLASS_SUN, 404), (records["class"], 404)):
        response = db_client.get("/api/v1" + path.format(classroom=classroom), headers=headers)
        assert response.status_code == status, response.text


def test_parent_note_classroom_filter_does_not_deny_or_log(db_client, records, seeded_db):
    headers = {"Authorization": "Bearer " + issue_token(users.get_user(seed.PARENT))}
    with seeded_db.connect() as connection:
        note_date = connection.scalar(text("SELECT note_date FROM daily_notes WHERE id=:id"),
                                      {"id": records["local_note"]})
        events_before = connection.scalar(text("SELECT count(*) FROM events WHERE action='permission_denied'"))
    for classroom, total in ((None, 1), (seed.CLASS_STAR, 1), (seed.CLASS_SUN, 0),
                             (records["class"], 0), (uuid4(), 0)):
        params = {"date": note_date.isoformat()}
        if classroom is not None:
            params["classroom_id"] = str(classroom)
        response = db_client.get("/api/v1/daily-notes", headers=headers, params=params)
        assert response.status_code == 200, response.text
        assert response.json()["total"] == total
        assert [n["id"] for n in response.json()["items"]] == ([str(records["local_note"])] if total else [])
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='permission_denied'")) == events_before


@pytest.mark.parametrize("method,path,actor", [
    ("POST", "/requests/{local_request}/slot-choices", seed.PARENT),
    ("POST", "/cards/{local_card}/bookings", seed.TEACHER),
    ("POST", "/memory-rules/{local_card}/decision", seed.TEACHER),
    ("POST", "/documents", seed.TEACHER),
    ("GET", "/documents/{local_card}", seed.TEACHER),
])
def test_pending_endpoints_fail_closed(db_client, records, method, path, actor):
    path = path.format(**records, local_class=seed.CLASS_STAR)
    headers = {"Authorization": "Bearer " + issue_token(users.get_user(actor)),
               "X-Request-ID": "pending-workflow"}
    response = db_client.request(method, "/api/v1" + path, headers=headers)
    assert response.status_code == 501, response.text
    assert response.json() == {"error": {
        "code": "NOT_IMPLEMENTED", "message": "DB 모드에서는 아직 준비 중인 기능이에요.",
        "trace_id": "pending-workflow", "details": {}}}
    # 학부모에게 위험 등급·보류 이유나 mock의 업무 데이터를 보내지 않는다.
    assert db_client.request(method, "/api/v1" + path).status_code == 401


def test_unknown_resource_and_other_org_have_identical_http_errors(db_client, records):
    headers = {"Authorization": "Bearer " + issue_token(users.get_user(seed.DIRECTOR)),
               "X-Request-ID": "same-error"}
    absent = db_client.get(f"/api/v1/requests/{uuid4()}", headers=headers)
    foreign = db_client.get(f"/api/v1/requests/{records['request']}", headers=headers)
    assert absent.status_code == foreign.status_code == 404
    assert absent.json() == foreign.json()


def test_pending_guard_leaves_validation_to_the_declared_route(db_client):
    headers = {"Authorization": "Bearer " + issue_token(users.get_user(seed.TEACHER))}
    for path in ("/requests/not-a-uuid", "/classrooms/not-a-uuid/children",
                 "/daily-notes?date=2026-11-20&classroom_id=not-a-uuid"):
        response = db_client.get("/api/v1" + path, headers=headers)
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_FAILED"
    # 선언하지 않은 쿼리는 mock처럼 무시해요. 받은함은 T27-b에서 연결했어요.
    assert db_client.get("/api/v1/cards?classroom_id=not-a-uuid", headers=headers).status_code == 200


@pytest.fixture
def boundary_records(seeded_db, records):
    values = {**records, "local_document": uuid4(), "document": uuid4(), "room": uuid4()}
    with seeded_db.begin() as connection:
        connection.execute(text("INSERT INTO rooms (id, org_id, name) VALUES (:room, :org, '[TEST] 상담실')"), values)
        for prefix, org in (("", records["org"]), ("local_", seed.ORG)):
            document_id = values[prefix + "document"]
            connection.execute(text("""
                INSERT INTO documents (id, org_id, title, doc_type, source, content_sha256)
                VALUES (:id, :org, '[TEST] 경계 자료', 'notice', 'virtual', :sha)
            """), {"id": document_id, "org": org, "sha": str(document_id)})
            values[prefix + "chunk"] = connection.scalar(text("""
                INSERT INTO document_chunks (document_id, org_id, chunk_index, content)
                VALUES (:id, :org, 0, '[TEST] 근거') RETURNING id
            """), {"id": document_id, "org": org})
    return {**values, "local_org": seed.ORG, "local_class": seed.CLASS_STAR,
            "local_parent": seed.PARENT, "local_teacher": seed.TEACHER,
            "local_other_teacher": seed.TEACHER_OTHER, "local_room": seed.ROOM}


@pytest.mark.parametrize("statement,foreign,local,constraint", [
    ("INSERT INTO children (org_id,classroom_id,display_name) VALUES (:local_org,:ref,'[TEST] 아이')",
     "class", "local_class", "children_classroom_id_org_id_fkey"),
    ("INSERT INTO child_guardians (org_id,child_id,user_id,relation) VALUES (:local_org,:child,:ref,'other')",
     "parent", "local_parent", "child_guardians_user_id_org_id_fkey"),
    ("INSERT INTO classroom_staff (org_id,classroom_id,user_id) VALUES (:local_org,:local_class,:ref)",
     "teacher", "local_other_teacher", "classroom_staff_user_id_org_id_fkey"),
    ("INSERT INTO card_evidence (org_id,card_id,chunk_id,rank) VALUES (:local_org,:local_card,:ref,1)",
     "chunk", "local_chunk", "card_evidence_chunk_id_org_id_fkey"),
    ("INSERT INTO consultation_slots (org_id,card_id,teacher_id,room_id,period,rank) "
     "VALUES (:local_org,:local_card,:ref,:local_room,:period,1)",
     "teacher", "local_teacher", "consultation_slots_teacher_id_org_id_fkey"),
    ("INSERT INTO consultation_slots (org_id,card_id,teacher_id,room_id,period,rank) "
     "VALUES (:local_org,:local_card,:local_teacher,:ref,:period,1)",
     "room", "local_room", "consultation_slots_room_id_org_id_fkey"),
    ("INSERT INTO events (org_id,request_id,actor_type,action) VALUES (:local_org,:ref,'system','created')",
     "request", "local_request", "events_request_id_org_id_fkey"),
    ("INSERT INTO notifications (org_id,recipient_id,kind,title,dedupe_key) "
     "VALUES (:local_org,:ref,'new_card','[TEST] 알림','[TEST] boundary')",
     "parent", "local_parent", "notifications_recipient_id_org_id_fkey"),
    ("INSERT INTO notifications (org_id,recipient_id,card_id,kind,title,dedupe_key) "
     "VALUES (:local_org,:local_parent,:ref,'new_card','[TEST] 알림','[TEST] boundary')",
     "card", "local_card", "notifications_card_id_org_id_fkey"),
    ("INSERT INTO request_messages (org_id,request_id,sender_type,sender_id,body) "
     "VALUES (:local_org,:local_request,'user',:ref,'[TEST] 대화')",
     "teacher", "local_teacher", "request_messages_sender_id_org_id_fkey"),
    ("INSERT INTO documents (org_id,title,doc_type,source,uploaded_by,content_sha256) "
     "VALUES (:local_org,'[TEST] 자료','notice','uploaded',:ref,'[TEST] upload')",
     "teacher", "local_teacher", "documents_uploaded_by_org_id_fkey"),
    ("INSERT INTO memories (org_id,owner_id,kind,content,source_card_id) "
     "VALUES (:local_org,:local_teacher,'tone','[TEST] 기억',:ref)",
     "card", "local_card", "memories_source_card_id_org_id_fkey"),
    ("INSERT INTO consultation_bookings (org_id,request_id,teacher_id,room_id,period,confirmed_by) "
     "VALUES (:local_org,:local_request,:local_teacher,:local_room,:period,:ref)",
     "teacher", "local_teacher", "consultation_bookings_confirmed_by_org_id_fkey"),
    ("INSERT INTO daily_notes (org_id,input_id,child_id,note_date) "
     "VALUES (:local_org,:local_input,:child,:ref)",
     "wrong_date", "date", "daily_notes_input_id_org_id_note_date_fkey"),
    ("INSERT INTO document_classrooms (org_id,document_id,classroom_id) "
     "VALUES (:local_org,:local_document,:ref)",
     "class", "local_class", "document_classrooms_classroom_id_org_id_fkey"),
], ids=["foreign_class", "foreign_parent", "foreign_staff", "B1", "B2", "B3", "B4", "B5",
        "B6", "B7", "B8", "B9", "B10", "B11", "B13"])
def test_database_boundary_rejects_only_foreign_reference(seeded_db, boundary_records,
                                                          statement, foreign, local, constraint):
    with seeded_db.connect() as connection:
        today = connection.scalar(text("SELECT CURRENT_DATE"))
        values = {**boundary_records, "child": seed.demo_id("5401"), "date": today,
                  "wrong_date": today + timedelta(days=1),
                  "period": "[2026-11-20 10:00+09,2026-11-20 10:30+09)"}
        with pytest.raises(IntegrityError) as error, connection.begin_nested():
            connection.execute(text(statement), {**values, "ref": values[foreign]})
        assert error.value.orig.sqlstate == "23503"
        assert error.value.orig.diag.constraint_name == constraint
        # 같은 SQL의 참조만 이 원 값으로 바꾸면 저장된다. 시험 종료 때 되돌린다.
        connection.execute(text(statement), {**values, "ref": values[local]})


def test_scope_functions_share_caller_connection_and_leave_rollback_to_caller(seeded_db, records):
    user = users.get_user(seed.TEACHER)
    with seeded_db.connect() as connection:
        tx = connection.begin()
        connection.execute(text("UPDATE requests SET title='[TEST] 미커밋' WHERE id=:id"), {"id": records["local_request"]})
        assert scope.request_in_scope(user, records["local_request"], connection=connection)["title"] == "[TEST] 미커밋"
        connection.execute(text("UPDATE children SET display_name='[TEST] 미커밋' WHERE id=:id"), {"id": seed.CHILD})
        assert scope.child_in_scope(user, seed.CHILD, connection=connection)["display_name"] == "[TEST] 미커밋"
        connection.execute(text("UPDATE classrooms SET name='[TEST] 미커밋' WHERE id=:id"), {"id": seed.CLASS_STAR})
        assert scope.classroom_in_scope(user, seed.CLASS_STAR, connection=connection)["name"] == "[TEST] 미커밋"
        connection.execute(text("UPDATE cards SET version=7 WHERE id=:id"), {"id": records["local_card"]})
        assert scope.card_in_scope(user, records["local_card"], connection=connection)["version"] == 7
        connection.execute(text("UPDATE daily_note_inputs SET activities='[TEST] 미커밋' WHERE id=:id"), {"id": records["local_input"]})
        assert scope.note_input_in_scope(user, records["local_input"], connection=connection)["activities"] == "[TEST] 미커밋"
        connection.execute(text("UPDATE daily_notes SET status='draft' WHERE id=:id"), {"id": records["local_note"]})
        assert scope.note_in_scope(user, records["local_note"], connection=connection)["status"] == "draft"
        tx.rollback()
    assert scope.card_in_scope(user, records["local_card"])["version"] == 1
    assert scope.note_in_scope(user, records["local_note"])["status"] == "sent"


def test_denial_audit_survives_caller_transaction_rollback(seeded_db, records):
    with pytest.raises(ApiError):
        with seeded_db.begin() as connection:
            connection.execute(text("UPDATE classrooms SET name='[TEST] 되돌릴 변경' WHERE id=:id"), {"id": seed.CLASS_STAR})
            scope.request_in_scope(users.get_user(seed.TEACHER_OTHER), records["local_request"], connection=connection)
    with seeded_db.connect() as connection:
        assert connection.scalar(text("SELECT name FROM classrooms WHERE id=:id"), {"id": seed.CLASS_STAR}) != "[TEST] 되돌릴 변경"
        assert connection.scalar(text("SELECT count(*) FROM events WHERE action='permission_denied'")) == 1


@pytest.mark.parametrize("kind", ["daily_note", "rule_proposal"])
def test_cards_without_request_have_literal_classroom_or_owner_scope(seeded_db, records, kind):
    card_id = uuid4()
    with seeded_db.begin() as connection:
        if kind == "rule_proposal":
            subject_id = connection.scalar(text("""
                INSERT INTO memory_rules (org_id,owner_id,reason_code,rule_text,rule_json)
                VALUES (:org,:owner,'tone','[TEST] 규칙','{}') RETURNING id
            """), {"org": seed.ORG, "owner": seed.TEACHER})
            subject_type = "memory_rule"
        else:
            subject_id, subject_type = records["local_input"], "daily_note_batch"
        connection.execute(text("""
            INSERT INTO cards (id,org_id,subject_type,subject_id,kind,assignee_id)
            VALUES (:id,:org,:type,:subject,:kind,:owner)
        """), {"id": card_id, "org": seed.ORG, "type": subject_type, "subject": subject_id, "kind": kind, "owner": seed.TEACHER})
    for actor in (seed.TEACHER, seed.DIRECTOR):
        row = scope.card_in_scope(users.get_user(actor), card_id)
        assert row["request_id"] is None and row["request_type"] is None
        assert row["classroom_id"] == (seed.CLASS_STAR if kind == "daily_note" else None)
    for actor, code in ((seed.TEACHER_OTHER, 404), (seed.PARENT, 403), (records["teacher"], 404)):
        with pytest.raises(ApiError) as error:
            scope.card_in_scope(users.get_user(actor), card_id)
        assert error.value.status == code
    with seeded_db.begin() as connection:
        connection.execute(text("""
            INSERT INTO classroom_staff (org_id,classroom_id,user_id) VALUES (:org,:class,:user)
        """), {"org": seed.ORG, "class": seed.CLASS_STAR, "user": seed.TEACHER_OTHER})
    if kind == "daily_note":
        assert scope.card_in_scope(users.get_user(seed.TEACHER_OTHER), card_id)["id"] == card_id
    else:
        with pytest.raises(ApiError):
            scope.card_in_scope(users.get_user(seed.TEACHER_OTHER), card_id)
