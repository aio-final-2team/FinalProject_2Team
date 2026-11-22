-- 유치온 DB 스키마 초안 (T09) · 문서 버전 v0.17 ([제안][선택] T56 화상상담 11/22 반영)
-- 설계서: Docs/Step2/DB_스키마_설계서.md
-- 이 파일은 최종 설계 모양이다. 실제 적용은 apps/api/migrations의 0001 → 0002 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009 → 0010 → 0011로 한다.
-- 대상: PostgreSQL 16 + pgvector 0.8 (compose.yaml의 pgvector/pgvector:pg16). Supabase는 쓰지 않는다(설계서 5.1)
-- 기관 경계: 기관에 속한 표끼리는 (id, org_id) 짝으로 참조해서 다른 원 행을 섞어 넣으면 DB가 거부한다

CREATE EXTENSION IF NOT EXISTS vector;      -- 문서 조각 임베딩
CREATE EXTENSION IF NOT EXISTS btree_gist;  -- 상담실·담임 시간 겹침 막기(EXCLUDE)
-- gen_random_uuid()는 PostgreSQL 13부터 기본 제공

-- ─────────────────────────────────────────────
-- 1. 기관·반·계정
-- ─────────────────────────────────────────────

CREATE TABLE organizations (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name        text NOT NULL,
    kind        text NOT NULL DEFAULT 'private_kindergarten'
                CHECK (kind IN ('private_kindergarten', 'public_kindergarten', 'daycare')),
    region      text,
    is_virtual  boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE classrooms (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid NOT NULL REFERENCES organizations(id),
    name         text NOT NULL,
    age_group    smallint CHECK (age_group BETWEEN 3 AND 5),
    school_year  smallint NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, school_year, name),
    UNIQUE (id, org_id)                    -- 다른 표가 (반, 기관) 짝을 함께 참조
);

CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL REFERENCES organizations(id),
    role           text NOT NULL CHECK (role IN ('parent', 'teacher', 'director')),
    title          text,                   -- 원장·원감 같은 직함 표시용
    display_name   text NOT NULL,
    login_id       text NOT NULL UNIQUE,
    password_hash  text NOT NULL,          -- argon2 또는 bcrypt 해시만 저장
    token_version  integer NOT NULL DEFAULT 0,  -- 올리면 이전 JWT가 모두 무효
    is_active      boolean NOT NULL DEFAULT true,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, org_id)
);

-- 담임·부담임·대체 담임 배정. 기간이 비어 있으면 계속 담당
CREATE TABLE classroom_staff (
    classroom_id  uuid NOT NULL,
    org_id        uuid NOT NULL,
    user_id       uuid NOT NULL,
    is_homeroom   boolean NOT NULL DEFAULT true,
    valid_from    date,                    -- 대체 담임 기간(T04 7.1). 그 기간에만 그 반 자료를 봄
    valid_to      date,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (classroom_id, user_id),
    CHECK (valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from),
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id),
    FOREIGN KEY (user_id, org_id) REFERENCES users(id, org_id)
);

CREATE TABLE children (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL,
    classroom_id  uuid NOT NULL,
    display_name  text NOT NULL,           -- 가상 이름만
    is_virtual    boolean NOT NULL DEFAULT true,
    created_at    timestamptz NOT NULL DEFAULT now(),
    photo_scope   text NOT NULL DEFAULT 'family'
                  CONSTRAINT children_photo_scope_check CHECK (photo_scope IN ('family', 'class', 'org')),
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id),
    UNIQUE (id, org_id)
);

CREATE TABLE child_guardians (
    child_id  uuid NOT NULL,
    org_id    uuid NOT NULL,
    user_id   uuid NOT NULL,
    relation  text NOT NULL CHECK (relation IN ('mother', 'father', 'grandparent', 'other')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (child_id, user_id),
    FOREIGN KEY (child_id, org_id) REFERENCES children(id, org_id),
    FOREIGN KEY (user_id, org_id) REFERENCES users(id, org_id)
);

-- ─────────────────────────────────────────────
-- 2. 요청·대화
-- ─────────────────────────────────────────────

CREATE TABLE requests (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           uuid NOT NULL,
    classroom_id     uuid,
    child_id         uuid,
    requester_id     uuid NOT NULL,
    client_request_id text NOT NULL,       -- 화면이 만든 요청 키. 같은 제출을 두 번 받지 않음
    type             text NOT NULL
                     CHECK (type IN ('inquiry', 'consultation', 'complaint', 'medication', 'pickup')),
    title            text,
    body             text NOT NULL,
    status           text NOT NULL DEFAULT 'received'
                     CHECK (status IN ('received', 'classified', 'needs_info', 'assigned',
                                       'awaiting_review', 'approved', 'sent_or_booked', 'completed',
                                       'on_hold', 'escalated', 'rejected')),
    urgency          text CHECK (urgency IN ('low', 'normal', 'high', 'urgent')),  -- 모든 요청의 급한 정도(정렬용)
    risk_level       text CHECK (risk_level IN ('normal', 'urgent', 'uncertain')),  -- 민원 위험 등급: 일반·긴급·판단 필요(T04 2.3)
    risk_category    text CHECK (risk_category IN ('child_safety', 'staff_attack',
                                                   'legal_external', 'privacy_leak')),  -- 긴급 4가지
    risk_confidence  real CHECK (risk_confidence BETWEEN 0 AND 1),  -- 기준값은 T06 평가로 정함
    topic_key        text,                 -- 감독 AI가 정해진 주제 10개 + 'other'(계약표 6장 ②, T10 회의 11/18)에서 고른 민원 주제. 같은 주제 반복 횟수 계산용('other'는 안 셈)
    parent_confirmed_at timestamptz,       -- 민원 회신에 학부모가 '확인했어요'를 누른 시각(T04 합의 2)
    missing_fields   jsonb NOT NULL DEFAULT '[]',
    assignee_id      uuid,
    previous_request_id uuid,              -- 끝난 요청을 다시 열 때 잇는 이전 요청(T04 2.1)
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    closed_at        timestamptz,
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id),
    FOREIGN KEY (child_id, org_id) REFERENCES children(id, org_id),
    FOREIGN KEY (requester_id, org_id) REFERENCES users(id, org_id),
    FOREIGN KEY (assignee_id, org_id) REFERENCES users(id, org_id),
    FOREIGN KEY (previous_request_id, org_id) REFERENCES requests(id, org_id),
    UNIQUE (requester_id, client_request_id),
    UNIQUE (id, org_id),
    CHECK (previous_request_id IS DISTINCT FROM id),
    CHECK (risk_level IS NULL OR type = 'complaint'),
    CHECK (risk_level IS DISTINCT FROM 'urgent' OR risk_category IS NOT NULL),
    CHECK (parent_confirmed_at IS NULL OR type = 'complaint')
);
CREATE INDEX requests_org_status_idx   ON requests (org_id, status);
CREATE INDEX requests_class_time_idx   ON requests (classroom_id, created_at DESC);
CREATE INDEX requests_requester_idx    ON requests (requester_id, created_at DESC);
-- 같은 내용 민원 = 같은 반 · 최근 30일 · 같은 주제, 보낸 학부모가 달라도 합산(T04 합의 3)
CREATE INDEX requests_repeat_idx       ON requests (classroom_id, topic_key, created_at)
    WHERE type = 'complaint' AND topic_key IS NOT NULL;

-- 학부모 요청 화면 오른쪽 대화
CREATE TABLE request_messages (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id   uuid NOT NULL,
    org_id       uuid NOT NULL,
    sender_type  text NOT NULL CHECK (sender_type IN ('user', 'agent', 'system')),
    sender_id    uuid,                     -- 사람일 때만
    body         text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (request_id, org_id) REFERENCES requests(id, org_id),
    FOREIGN KEY (sender_id, org_id) REFERENCES users(id, org_id)
);
CREATE INDEX request_messages_req_idx ON request_messages (request_id, id);

-- ─────────────────────────────────────────────
-- 3. 자료 창고·문서 조각
-- ─────────────────────────────────────────────

CREATE TABLE documents (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organizations(id),
    title           text NOT NULL,
    doc_type        text NOT NULL
                    CHECK (doc_type IN ('notice', 'schedule', 'menu', 'policy',
                                        'consult_timetable', 'law', 'public_data')),
    visibility      text NOT NULL DEFAULT 'all'
                    CHECK (visibility IN ('staff', 'parents', 'all')),
    source          text NOT NULL CHECK (source IN ('uploaded', 'virtual', 'public_api')),
    source_url      text,
    api_called_at   timestamptz,           -- 공공 API를 실제로 불러 온 시각. 목록만 본 API는 비워 둠
    effective_from  date,
    effective_to    date,
    status          text NOT NULL DEFAULT 'active'
                    CHECK (status IN ('active', 'conflict_pending', 'superseded')),
    -- 자료 올리기는 202로 접수하고 조각 나누기·임베딩·충돌 검사를 뒤에서 함. 화면은 이 값으로 진행·실패를 봄(T13 6.3)
    -- 실패 이유는 events(tool_failed)의 detail에 남김. 조각은 succeeded가 될 때 한 번에 넣음
    ingest_status   text NOT NULL DEFAULT 'queued'
                    CHECK (ingest_status IN ('queued', 'running', 'succeeded', 'failed')),
    supersedes_id   uuid,                  -- 이 문서가 대신하는 옛 판. 옛 판은 superseded가 됨(T04 합의 7)
    uploaded_by     uuid,
    content_sha256  text NOT NULL,
    is_virtual      boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (uploaded_by, org_id) REFERENCES users(id, org_id),
    FOREIGN KEY (supersedes_id, org_id) REFERENCES documents(id, org_id),
    UNIQUE (org_id, content_sha256),
    UNIQUE (id, org_id),
    UNIQUE (supersedes_id),                -- 한 판을 대신하는 새 판은 하나
    CHECK (supersedes_id IS DISTINCT FROM id),
    CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);

CREATE TABLE document_chunks (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id      uuid NOT NULL,
    org_id           uuid NOT NULL,
    chunk_index      integer NOT NULL,
    location         text,                 -- 근거 위치 표시용(예: '2쪽 3항')
    content          text NOT NULL,
    embedding        vector(1024),         -- bge-m3 출력 차원 1024. 모델·차원을 바꾸면 다시 색인
    embedding_model  text,                 -- 예: 'BAAI/bge-m3'
    embedding_version text,                -- 모델 판·색인 판. 판이 다른 벡터는 섞어 검색하지 않음
    created_at       timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (document_id, org_id) REFERENCES documents(id, org_id) ON DELETE CASCADE,
    UNIQUE (document_id, chunk_index),
    UNIQUE (id, org_id)
);
-- 인덱스 연산자 vector_cosine_ops ↔ 검색식 연산자 <=>(코사인 거리). 둘이 다르면 인덱스를 안 탐
CREATE INDEX document_chunks_embedding_idx ON document_chunks
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX document_chunks_org_idx ON document_chunks (org_id, document_id);

-- 반 자료의 대상 반. 대상 반마다 한 줄, 줄이 없으면 원 전체 자료(v0.6).
-- 한 통신문이 여러 반 대상일 수 있고(예: 김장 체험 만 4·5세반), 같은 파일은 documents에 한 번만 들어가서(content_sha256) 반마다 문서를 따로 둘 수 없다
CREATE TABLE document_classrooms (
    document_id   uuid NOT NULL,
    classroom_id  uuid NOT NULL,
    org_id        uuid NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (document_id, classroom_id),
    FOREIGN KEY (document_id, org_id) REFERENCES documents(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id)
);
CREATE INDEX document_classrooms_class_idx ON document_classrooms (classroom_id, document_id);

-- ─────────────────────────────────────────────
-- 4. 승인 카드·결정·근거
-- ─────────────────────────────────────────────

CREATE TABLE cards (
    id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id           uuid NOT NULL,
    request_id       uuid,                 -- 알림장 묶음 카드는 요청이 없음
    subject_type     text CHECK (subject_type IN ('daily_note_batch', 'memory_rule')),
    subject_id       uuid,
    kind             text NOT NULL
                     CHECK (kind IN ('reply_draft', 'consult_slots', 'director_report',
                                     'needs_info', 'daily_note', 'rule_proposal')),
    status           text NOT NULL DEFAULT 'unassigned'
                     CHECK (status IN ('unassigned', 'pending', 'in_review', 'on_hold',
                                       'approved', 'rejected', 'done')),
    assignee_id      uuid,
    due_at           timestamptz,          -- 지나면 원장 현황에서 '지연'. API가 주말·공휴일을 건너뛰고 계산(긴급·판단 필요 2시간은 그대로, 계약표 6장 ⑤)
    hold_until       date,                 -- 보류 예정일. 학부모 화면에 보임(보류 이유는 교직원끼리만)
    draft            jsonb NOT NULL DEFAULT '{}',   -- AI 초안
    check_result     jsonb,                -- 검사 AI 결과(통과 여부·짚은 항목)
    check_attempts   smallint NOT NULL DEFAULT 0 CHECK (check_attempts BETWEEN 0 AND 2),
    graph_thread_id  text,                 -- LangGraph 체크포인트 thread_id
    version          integer NOT NULL DEFAULT 1,    -- 낙관적 잠금. 바뀔 때마다 +1
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    closed_at        timestamptz,
    FOREIGN KEY (request_id, org_id) REFERENCES requests(id, org_id),
    FOREIGN KEY (assignee_id, org_id) REFERENCES users(id, org_id),
    UNIQUE (id, org_id),
    CHECK (request_id IS NOT NULL OR subject_id IS NOT NULL),
    CHECK (status <> 'on_hold' OR hold_until IS NOT NULL),
    CHECK (kind <> 'director_report' OR assignee_id IS NOT NULL)  -- 원장 보고 카드는 원장 ID로 만듦
);
CREATE INDEX cards_inbox_idx   ON cards (org_id, assignee_id, status)
    WHERE status IN ('unassigned', 'pending', 'in_review', 'on_hold');
CREATE INDEX cards_request_idx ON cards (request_id);
CREATE INDEX cards_due_idx     ON cards (org_id, due_at)
    WHERE status IN ('unassigned', 'pending', 'in_review', 'on_hold');

-- 카드가 댄 근거(문서명·위치·적용일을 화면에 보여 줌)
CREATE TABLE card_evidence (
    card_id      uuid NOT NULL,
    org_id       uuid NOT NULL,
    chunk_id     bigint NOT NULL,
    rank         smallint NOT NULL,
    score        real,
    quote        text,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (card_id, chunk_id),
    FOREIGN KEY (card_id, org_id) REFERENCES cards(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (chunk_id, org_id) REFERENCES document_chunks(id, org_id)  -- 다른 원 자료를 근거로 못 댐
);

-- 사람의 결정. 카드 판(version)마다 결정은 한 번만 → 재개·승인 버튼을 여러 번 눌러도 한 번만 처리
CREATE TABLE approvals (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    card_id         uuid NOT NULL,
    org_id          uuid NOT NULL,
    card_version    integer NOT NULL,
    decided_by      uuid NOT NULL,
    -- reject = 거절(초안 다시) · dismiss = 반려(요청을 처리하지 않음) · complete = 민원 처리 완료(T04 합의 2)
    -- resume = 보류 재개 · escalate = 담임이 원장님께 올리기(T04 8장 #5) · instruct = 원장 지시(내용은 reason_text)
    decision        text NOT NULL CHECK (decision IN ('approve', 'edit_approve', 'reject', 'hold',
                                                      'resume', 'dismiss', 'complete',
                                                      'escalate', 'instruct')),
    -- 거절·반려 이유 코드(기억·규칙 제안에 씀). 값 목록은 설정값이라 CHECK로 묶지 않음(설계서 2.2):
    -- wrong_fact · tone · missing_info · privacy · policy · slot_unavailable · room_unavailable · other
    reason_code     text,
    reason_text     text,
    edited_content  jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (card_id, org_id) REFERENCES cards(id, org_id),
    FOREIGN KEY (decided_by, org_id) REFERENCES users(id, org_id),
    UNIQUE (card_id, card_version),
    CHECK (decision NOT IN ('reject', 'dismiss') OR reason_code IS NOT NULL),
    CHECK (decision NOT IN ('hold', 'instruct') OR reason_text IS NOT NULL),
    CHECK (reason_code IS DISTINCT FROM 'other' OR reason_text IS NOT NULL)   -- 기타면 이유 글 필수
);

-- 학부모가 '확인했어요'를 누르지 않은 민원을 처리 완료하려면 이유 글이 있어야 함(계약표 6장 ⑦, T10 회의 11/18)
-- 다른 표(requests)의 값을 봐야 해서 CHECK 대신 트리거로 막음
CREATE FUNCTION require_reason_for_unconfirmed_complete() RETURNS trigger AS $$
BEGIN
    IF NEW.decision = 'complete' AND NEW.reason_text IS NULL AND EXISTS (
        SELECT 1 FROM cards c
        JOIN requests r ON r.id = c.request_id AND r.org_id = c.org_id
        WHERE c.id = NEW.card_id AND c.org_id = NEW.org_id AND r.parent_confirmed_at IS NULL
    ) THEN
        RAISE EXCEPTION 'complete without parent confirmation needs reason_text'
            USING ERRCODE = 'check_violation';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER approvals_unconfirmed_complete_reason
    BEFORE INSERT ON approvals
    FOR EACH ROW EXECUTE FUNCTION require_reason_for_unconfirmed_complete();

-- ─────────────────────────────────────────────
-- 5. 처리 이력(지우지 않고 쌓기만)
-- ─────────────────────────────────────────────

CREATE TABLE events (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id       uuid NOT NULL REFERENCES organizations(id),
    request_id   uuid,
    card_id      uuid,
    actor_type   text NOT NULL CHECK (actor_type IN ('user', 'agent', 'system')),
    actor_id     uuid,
    agent_name   text,                     -- 감독·자료·기억·검사 AI 등
    action       text NOT NULL
                 CHECK (action IN ('created', 'classified', 'info_requested', 'assigned',
                                   'reassigned', 'drafted', 'checked', 'returned',
                                   'approved', 'rejected', 'held', 'resumed', 'escalated', 'instructed',
                                   'sent', 'booked', 'completed', 'tool_called',
                                   'tool_failed', 'permission_denied',
                                   'parent_confirmed', 'risk_reclassified', 'dismissed',
                                   'answered_from_saved', 'slot_hold_expired',
                                   'daily_note_drafted', 'daily_note_edited', 'daily_note_confirmed', 'daily_note_sent', 'agent_requeued',
                                   'consultation_delay_reported', 'consultation_reminded',
                                   'feed_post_created', 'feed_post_deleted', 'feed_post_hidden', 'photo_scope_changed',
                                   'video_joined', 'video_left')),
    -- 시스템이 한 일(보류 예정일 자동 재개, 상담 시간 잡아 두기 풀림)은 actor_type = 'system', actor_id = NULL
    from_status  text,
    to_status    text,
    detail       jsonb NOT NULL DEFAULT '{}',   -- 비밀값·불필요한 개인정보는 넣지 않음
    created_at   timestamptz NOT NULL DEFAULT now(),
    daily_note_id uuid,                 -- 아이별 알림장 연결(v0.9)
    FOREIGN KEY (request_id, org_id) REFERENCES requests(id, org_id),
    FOREIGN KEY (card_id, org_id) REFERENCES cards(id, org_id),
    FOREIGN KEY (actor_id, org_id) REFERENCES users(id, org_id)
);
CREATE INDEX events_request_idx ON events (request_id, id);
CREATE INDEX events_card_idx    ON events (card_id, id);
CREATE INDEX events_daily_note_idx ON events (daily_note_id, id);
CREATE INDEX events_org_time_idx ON events (org_id, created_at DESC);

-- ─────────────────────────────────────────────
-- 6. 상담 예약(자산 = 상담실)
-- ─────────────────────────────────────────────

CREATE TABLE rooms (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid NOT NULL REFERENCES organizations(id),
    name       text NOT NULL,
    is_active  boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (org_id, name),
    UNIQUE (id, org_id)
);

-- 담임 일정(수업·회의 등 상담이 안 되는 시간). 시연은 가상 상담 시간표에서 채움
CREATE TABLE staff_busy_blocks (
    id        bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id    uuid NOT NULL,
    user_id   uuid NOT NULL,
    period    tstzrange NOT NULL,
    kind      text NOT NULL CHECK (kind IN ('class', 'meeting', 'duty', 'off', 'other')),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (user_id, org_id) REFERENCES users(id, org_id)
);
CREATE INDEX staff_busy_blocks_idx ON staff_busy_blocks USING gist (user_id, period);

-- 일정 계산 코드가 낸 후보(회차마다 최대 3개). 거절·충돌로 다시 내면 같은 카드에 round를 올림(T04 4.1)
CREATE TABLE consultation_slots (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    card_id     uuid NOT NULL,
    org_id      uuid NOT NULL,
    teacher_id  uuid NOT NULL,
    room_id     uuid NOT NULL,
    period      tstzrange NOT NULL,
    round       smallint NOT NULL DEFAULT 1 CHECK (round >= 1),
    rank        smallint NOT NULL CHECK (rank BETWEEN 1 AND 3),
    status      text NOT NULL DEFAULT 'proposed'
                CHECK (status IN ('proposed', 'chosen_by_parent', 'confirmed', 'discarded')),
    chosen_at   timestamptz,               -- 학부모가 체크한 시각. 이때부터 24시간 그 시간을 잡아 둠(계약표 6장 ⑥)
    created_at  timestamptz NOT NULL DEFAULT now(),
    CHECK (status <> 'chosen_by_parent' OR chosen_at IS NOT NULL),
    FOREIGN KEY (card_id, org_id) REFERENCES cards(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (teacher_id, org_id) REFERENCES users(id, org_id),
    FOREIGN KEY (room_id, org_id) REFERENCES rooms(id, org_id),
    UNIQUE (card_id, round, rank),
    UNIQUE (id, org_id)
);

-- 확정된 예약. 같은 상담실·같은 담임이 겹치는 시간은 DB가 저장을 거부함
CREATE TABLE consultation_bookings (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL,
    request_id    uuid NOT NULL,
    slot_id       bigint,                  -- 학부모가 체크한 후보. teacher_id·room_id·period는 이 후보에서 복사
    teacher_id    uuid NOT NULL,           -- 아래 배제 제약이 이 표 안의 칸만 볼 수 있어서 후보 값을 복사해 둠(설계서 1.4)
    room_id       uuid NOT NULL,
    period        tstzrange NOT NULL,
    status        text NOT NULL DEFAULT 'confirmed'
                  CHECK (status IN ('confirmed', 'cancelled', 'done')),
    confirmed_by  uuid NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    expected_end_at timestamptz,          -- 담임이 기록한 예상 종료. NULL이면 지연을 추측하지 않아요.
    FOREIGN KEY (request_id, org_id) REFERENCES requests(id, org_id),
    FOREIGN KEY (slot_id, org_id) REFERENCES consultation_slots(id, org_id),
    FOREIGN KEY (teacher_id, org_id) REFERENCES users(id, org_id),
    FOREIGN KEY (room_id, org_id) REFERENCES rooms(id, org_id),
    FOREIGN KEY (confirmed_by, org_id) REFERENCES users(id, org_id),
    CONSTRAINT consultation_bookings_expected_end_check
        CHECK (isfinite(expected_end_at) AND expected_end_at > upper(period)),
    CONSTRAINT consultation_bookings_delay_bounds_check
        CHECK (expected_end_at <= upper(period) + interval '3 hours'
          AND (expected_end_at AT TIME ZONE 'Asia/Seoul')::date
              = (lower(period) AT TIME ZONE 'Asia/Seoul')::date),
    EXCLUDE USING gist (room_id WITH =, period WITH &&) WHERE (status = 'confirmed'),
    EXCLUDE USING gist (teacher_id WITH =, period WITH &&) WHERE (status = 'confirmed')
);
CREATE UNIQUE INDEX consultation_bookings_one_per_request
    ON consultation_bookings (request_id) WHERE status = 'confirmed';

-- ─────────────────────────────────────────────
-- 7. 기억·개인 규칙
-- ─────────────────────────────────────────────

CREATE TABLE memories (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          uuid NOT NULL,
    owner_id        uuid NOT NULL,
    kind            text NOT NULL
                    CHECK (kind IN ('rejection_reason', 'preference', 'tone')),
    reason_code     text,                  -- 거절 이유면 approvals.reason_code와 같은 값
    content         text NOT NULL,
    structured      jsonb NOT NULL DEFAULT '{}',   -- 예: {"weekday": 3, "before": "14:00"}
    source_card_id  uuid,
    created_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz,           -- 사용자가 지우면 표시하고 다음 제안에서 뺌
    FOREIGN KEY (owner_id, org_id) REFERENCES users(id, org_id),
    FOREIGN KEY (source_card_id, org_id) REFERENCES cards(id, org_id)
);
CREATE INDEX memories_owner_idx ON memories (owner_id, kind, reason_code)
    WHERE deleted_at IS NULL;

-- 같은 거절 이유가 3번 쌓이면 제안. 담임이 승인해야 active
CREATE TABLE memory_rules (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id       uuid NOT NULL,
    owner_id     uuid NOT NULL,
    reason_code  text NOT NULL,
    rule_text    text NOT NULL,
    rule_json    jsonb NOT NULL,
    status       text NOT NULL DEFAULT 'proposed'
                 CHECK (status IN ('proposed', 'active', 'off', 'declined')),
    created_at   timestamptz NOT NULL DEFAULT now(),   -- 제안된 시각
    decided_at   timestamptz,
    FOREIGN KEY (owner_id, org_id) REFERENCES users(id, org_id)
);
CREATE UNIQUE INDEX memory_rules_one_open
    ON memory_rules (owner_id, reason_code) WHERE status IN ('proposed', 'active');

-- 원에 남은 답(FR-20). 담임이 승인한 문의 답을 원 단위로 저장. 개인 기억(memories)과 따로 둠
-- 바로 답하는 조건: 질문 뜻이 충분히 같고 근거 문서가 최신일 때만(T04 합의 7)
CREATE TABLE saved_answers (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id              uuid NOT NULL,
    classroom_id        uuid,              -- 없으면 원 전체에 쓰는 답
    question            text NOT NULL,
    question_embedding  vector(1024) NOT NULL,
    embedding_model     text NOT NULL,
    embedding_version   text,
    answer              text NOT NULL,
    source_card_id      uuid NOT NULL,
    approved_by         uuid NOT NULL,
    status              text NOT NULL DEFAULT 'active'
                        CHECK (status IN ('active', 'off', 'invalidated')),  -- off = 담임이 끔 → 다시 카드로 물음(FR-20)
    invalidated_at      timestamptz,
    invalidated_reason  text,
    created_at          timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id),
    FOREIGN KEY (source_card_id, org_id) REFERENCES cards(id, org_id),
    FOREIGN KEY (approved_by, org_id) REFERENCES users(id, org_id),
    UNIQUE (id, org_id),
    CHECK (status <> 'invalidated' OR invalidated_at IS NOT NULL)
);
CREATE INDEX saved_answers_embedding_idx ON saved_answers
    USING hnsw (question_embedding vector_cosine_ops) WHERE status = 'active';

-- 답이 근거로 쓴 문서
CREATE TABLE saved_answer_sources (
    saved_answer_id  uuid NOT NULL,
    org_id           uuid NOT NULL,
    document_id      uuid NOT NULL,
    created_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (saved_answer_id, document_id),
    FOREIGN KEY (saved_answer_id, org_id) REFERENCES saved_answers(id, org_id) ON DELETE CASCADE,
    FOREIGN KEY (document_id, org_id) REFERENCES documents(id, org_id)
);
CREATE INDEX saved_answer_sources_doc_idx ON saved_answer_sources (document_id);

-- 근거 문서가 새 판으로 바뀌거나(superseded) 충돌 확인 대기가 되면 그 문서를 쓴 답을 자동으로 무효로 함
-- 꺼 둔(off) 답도 무효로 해서, 나중에 다시 켜도 옛 판 근거로 답하지 않게 함
CREATE FUNCTION invalidate_saved_answers() RETURNS trigger AS $$
BEGIN
    UPDATE saved_answers sa
       SET status = 'invalidated', invalidated_at = now(),
           invalidated_reason = 'document_' || NEW.status
     WHERE sa.status IN ('active', 'off')
       AND sa.id IN (SELECT saved_answer_id FROM saved_answer_sources WHERE document_id = NEW.id);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER documents_invalidate_saved_answers
    AFTER UPDATE OF status ON documents
    FOR EACH ROW
    WHEN (OLD.status = 'active' AND NEW.status <> 'active')
    EXECUTE FUNCTION invalidate_saved_answers();

-- ─────────────────────────────────────────────
-- 8. 알림장(글 초안)
-- ─────────────────────────────────────────────

-- 교사가 반 단위로 넣는 그날 활동·준비물
CREATE TABLE daily_note_inputs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL,
    classroom_id  uuid NOT NULL,
    note_date     date NOT NULL,
    activities    text,
    supplies      text,
    -- 알림장 초안은 202로 접수하고 AI가 뒤에서 아이별 초안을 만듦. 화면은 이 값으로 진행·실패를 봄(T13 6.3)
    draft_status  text NOT NULL DEFAULT 'queued'
                  CHECK (draft_status IN ('queued', 'running', 'succeeded', 'failed')),
    author_id     uuid NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now(),
    child_memos   jsonb NOT NULL DEFAULT '[]'::jsonb
                  CONSTRAINT daily_note_inputs_child_memos_array
                  CHECK (jsonb_typeof(child_memos) = 'array'),
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id),
    FOREIGN KEY (author_id, org_id) REFERENCES users(id, org_id),
    UNIQUE (classroom_id, note_date),
    UNIQUE (id, org_id, note_date)         -- 아이별 알림장이 (입력, 기관, 날짜) 짝으로 참조
);

-- 아이별 알림장. needs_check 항목이 남으면 보내지 못함
-- 아이 한 명 단위는 이 CHECK가 막고, '반에 하나라도 남으면 반 전체 잠금'(T04 합의 6)은 API가 한 트랜잭션에서 막음
CREATE TABLE daily_notes (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL,
    input_id       uuid NOT NULL,
    child_id       uuid NOT NULL,
    note_date      date NOT NULL,         -- 입력의 날짜와 같아야 함(아래 복합 FK). 아이·날짜 유니크에 씀
    status         text NOT NULL DEFAULT 'draft'
                   CHECK (status IN ('draft', 'needs_check', 'ready', 'sent')),
    content        jsonb NOT NULL DEFAULT '{}',  -- 하루·식사·투약/귀가 줄·준비물
    open_checks    jsonb NOT NULL DEFAULT '[]',  -- 검사 AI가 짚은 확인 필요 항목
    confirmed_by   uuid,                  -- 교사 확인(T04 6.1 note_ready = 교사가 확인함)
    confirmed_at   timestamptz,
    sent_at        timestamptz,
    created_at     timestamptz NOT NULL DEFAULT now(),
    ai_original    jsonb NOT NULL DEFAULT '{}',  -- 마지막 AI 초안. 교사 수정 때 유지, 미수정 초안 재생성 때 갱신(v0.9)
    CONSTRAINT daily_notes_id_org_key UNIQUE (id, org_id),
    FOREIGN KEY (input_id, org_id, note_date) REFERENCES daily_note_inputs(id, org_id, note_date),
    FOREIGN KEY (child_id, org_id) REFERENCES children(id, org_id),
    FOREIGN KEY (confirmed_by, org_id) REFERENCES users(id, org_id),
    UNIQUE (child_id, note_date),
    CHECK (status <> 'sent' OR jsonb_array_length(open_checks) = 0),
    CHECK (status NOT IN ('ready', 'sent') OR (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL))
);

ALTER TABLE events ADD CONSTRAINT events_daily_note_org_fkey
    FOREIGN KEY (daily_note_id, org_id) REFERENCES daily_notes(id, org_id);

-- ─────────────────────────────────────────────
-- 9. 서비스 안 알림
-- ─────────────────────────────────────────────

CREATE TABLE notifications (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id        uuid NOT NULL REFERENCES organizations(id),
    recipient_id  uuid NOT NULL,
    request_id    uuid,
    card_id       uuid,
    subject_type  text CHECK (subject_type IN ('daily_note')),  -- 요청·카드가 아닌 대상(알림장)
    subject_id    uuid,
    -- T04 9장 알림 시점 11가지 + 계약표 6장 기본값 2가지(⑥ 상담 시간 잡아 두기 풀림, ⑨ 보류 자동 재개)
    -- T48 상담 예정 종료 10분 전·명시된 지연의 대체 시간 제안 2가지 추가(v0.13)
    -- T46 투약·귀가 접수·교직원 확인 2가지 추가(v0.14, 팀 확인 전 초안)
    kind          text NOT NULL
                  CHECK (kind IN ('needs_info', 'new_card', 'urgent_complaint', 'uncertain_complaint',
                                  'director_report', 'on_hold', 'sent_or_booked', 'parent_confirmed',
                                  'completed', 'rejected', 'note_sent',
                                  'slot_hold_expired', 'hold_resumed',
                                  'consultation_ending', 'consultation_delayed', 'care_requested', 'care_confirmed')),
    title         text NOT NULL,
    body          text,
    dedupe_key    text NOT NULL UNIQUE,    -- 요청 이력 또는 상담 예약·종류·수신자 키(설계서 2.6). 같은 알림 두 번 안 감
    status        text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'sent', 'failed', 'held')),
    attempts      smallint NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    last_error    text,
    deliver_after timestamptz NOT NULL DEFAULT now(),   -- 근무 시간 밖 알림은 다음 근무 시작으로 미룸. 아이 안전 긴급만 바로(계약표 6장 ⑬)
    created_at    timestamptz NOT NULL DEFAULT now(),
    sent_at       timestamptz,
    read_at       timestamptz,
    next_attempt_at timestamptz NOT NULL DEFAULT now(), -- 노출 시각은 유지하고 다음 발송·재시도를 예약해요.
    FOREIGN KEY (recipient_id, org_id) REFERENCES users(id, org_id),
    FOREIGN KEY (request_id, org_id) REFERENCES requests(id, org_id),
    FOREIGN KEY (card_id, org_id) REFERENCES cards(id, org_id),
    CHECK ((subject_type IS NULL) = (subject_id IS NULL))
);
CREATE INDEX notifications_unread_idx ON notifications (recipient_id, created_at DESC)
    WHERE read_at IS NULL;
CREATE INDEX notifications_queue_idx ON notifications (deliver_after)
    WHERE status = 'pending';

-- ─────────────────────────────────────────────
-- 10. 평가 실행 기록(원장 현황의 '평가 결과', 모델 선택 근거)
-- ─────────────────────────────────────────────

CREATE TABLE eval_runs (
    id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    suite              text NOT NULL CHECK (suite IN ('bfcl', 'team30', 'service')),
    requested_model    text NOT NULL,
    returned_model     text,
    started_at         timestamptz NOT NULL,
    total              integer NOT NULL,
    passed             integer NOT NULL,
    errors             integer NOT NULL DEFAULT 0,
    report_url         text,
    note               text,
    created_at         timestamptz NOT NULL DEFAULT now(),   -- 기록한 시각(started_at은 평가를 시작한 시각)
    CHECK (passed + errors <= total)
);

-- ─────────────────────────────────────────────
-- 교직원 받은함 필터 6개(T04 2.2, 합의 5). 한 카드는 필터 하나에만 들어감
-- 긴급 민원은 따로 필터가 아니라 '확인 필요' 안에서 is_urgent로 맨 위에 올림
-- ─────────────────────────────────────────────

CREATE VIEW staff_inbox AS
SELECT
    c.id            AS card_id,
    c.org_id,
    c.assignee_id,
    c.kind,
    c.status        AS card_status,
    c.version,
    c.due_at,
    c.hold_until,
    c.closed_at,
    r.id            AS request_id,
    r.classroom_id,
    r.type          AS request_type,
    r.status        AS request_status,
    r.risk_level,
    r.parent_confirmed_at,
    (r.risk_level = 'urgent') IS TRUE AS is_urgent,
    CASE
        WHEN (c.status IN ('rejected', 'done') AND NOT (
                r.type = 'complaint' AND r.status = 'sent_or_booked'
                AND c.kind = 'reply_draft' AND c.status <> 'rejected') IS TRUE)
          OR r.status IN ('completed', 'rejected')
            THEN 'done'
        WHEN c.status = 'on_hold' OR r.status = 'on_hold'
            THEN 'on_hold'
        WHEN c.assignee_id IS NULL
            THEN 'unassigned'
        WHEN r.risk_level = 'uncertain'
            THEN 'uncertain'
        WHEN r.status IN ('awaiting_review', 'escalated')
          OR (r.type = 'complaint' AND r.status = 'sent_or_booked' AND r.parent_confirmed_at IS NOT NULL)
          OR (c.request_id IS NULL AND c.status IN ('pending', 'in_review'))
            THEN 'needs_review'
        ELSE 'in_progress'
    END AS inbox_filter
FROM cards c
LEFT JOIN requests r ON r.id = c.request_id;

-- ─────────────────────────────────────────────
-- 원장 현황(FR-19)은 표를 따로 두지 않고 받은함 뷰에서 센다
-- 미배정은 받은함 '미배정'(inbox_filter = 'unassigned')과 같은 기준
-- ─────────────────────────────────────────────

CREATE VIEW director_overview AS
SELECT
    i.org_id,
    count(*) FILTER (WHERE i.inbox_filter = 'unassigned')                             AS unassigned,
    count(*) FILTER (WHERE i.card_status IN ('pending', 'in_review', 'on_hold'))       AS waiting,
    count(*) FILTER (WHERE i.card_status IN ('pending', 'in_review', 'on_hold')
                       AND i.due_at < now())                                          AS delayed,
    count(*) FILTER (WHERE i.card_status = 'done'
                       AND i.closed_at >= date_trunc('day', now()))                   AS done_today,
    -- 학부모 확인 없이 담임이 이유를 남기고 끝낸 민원(최근 30일, 계약표 6장 ⑦). 요청마다 한 번만 셈
    count(DISTINCT i.request_id) FILTER (WHERE i.request_type = 'complaint'
                       AND i.request_status = 'completed'
                       AND i.parent_confirmed_at IS NULL
                       AND i.card_status = 'done'
                       AND i.closed_at >= now() - interval '30 days')                 AS completed_unconfirmed
FROM staff_inbox i
GROUP BY i.org_id;

-- [제안] T54: 피드·앨범. 사진 바이트는 MEDIA_DIR 파일에만 보관해요.
CREATE TABLE feed_posts (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL REFERENCES organizations(id),
    classroom_id  uuid,
    lane          text NOT NULL CHECK (lane IN ('class', 'org')),
    author_id     uuid NOT NULL,
    body          text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 2000 AND btrim(body) <> ''),
    status        text NOT NULL DEFAULT 'published' CHECK (status IN ('published', 'hidden')),
    created_at    timestamptz NOT NULL DEFAULT now(),
    deleted_at    timestamptz,
    CHECK ((lane='class' AND classroom_id IS NOT NULL) OR (lane='org' AND classroom_id IS NULL)),
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id),
    FOREIGN KEY (author_id, org_id) REFERENCES users(id, org_id),
    UNIQUE (id, org_id)
);
CREATE INDEX feed_posts_lane_time_idx ON feed_posts (org_id, lane, classroom_id, created_at DESC, id DESC)
    WHERE deleted_at IS NULL AND status='published';
CREATE TABLE feed_photos (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL,
    post_id       uuid NOT NULL,
    storage_path  text NOT NULL UNIQUE,
    media_type    text NOT NULL CHECK (media_type IN ('image/jpeg', 'image/png', 'image/webp')),
    size_bytes    integer NOT NULL CHECK (size_bytes BETWEEN 1 AND 5242880),
    sha256        text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    created_at    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (post_id, org_id) REFERENCES feed_posts(id, org_id),
    UNIQUE (id, org_id)
);
CREATE INDEX feed_photos_post_idx ON feed_photos (post_id, created_at, id);
CREATE TABLE feed_photo_children (
    org_id    uuid NOT NULL,
    photo_id  uuid NOT NULL,
    child_id  uuid NOT NULL,
    PRIMARY KEY (photo_id, child_id),
    FOREIGN KEY (photo_id, org_id) REFERENCES feed_photos(id, org_id),
    FOREIGN KEY (child_id, org_id) REFERENCES children(id, org_id)
);
CREATE INDEX feed_photo_children_child_idx ON feed_photo_children (child_id, photo_id);
