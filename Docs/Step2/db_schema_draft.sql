-- 유치온 DB 스키마 초안 (T09)
-- 설계서: Docs/Step2/DB_스키마_설계서.md
-- 이 파일은 설계 검토용이다. 실제 적용은 T19 마이그레이션(apps/api/migrations)으로 옮긴다.
-- 대상: PostgreSQL 16 + pgvector (compose.yaml의 pgvector/pgvector:pg16)

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

-- 담임·부담임 배정
CREATE TABLE classroom_staff (
    classroom_id  uuid NOT NULL,
    org_id        uuid NOT NULL,
    user_id       uuid NOT NULL,
    is_homeroom   boolean NOT NULL DEFAULT true,
    PRIMARY KEY (classroom_id, user_id),
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
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id),
    UNIQUE (id, org_id)
);

CREATE TABLE child_guardians (
    child_id  uuid NOT NULL,
    org_id    uuid NOT NULL,
    user_id   uuid NOT NULL,
    relation  text NOT NULL CHECK (relation IN ('mother', 'father', 'grandparent', 'other')),
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
    urgency          text CHECK (urgency IN ('low', 'normal', 'high', 'urgent')),
    topic_key        text,                 -- 감독 AI가 붙인 민원 주제. 같은 주제 반복 횟수 계산용
    missing_fields   jsonb NOT NULL DEFAULT '[]',
    assignee_id      uuid,
    created_at       timestamptz NOT NULL DEFAULT now(),
    updated_at       timestamptz NOT NULL DEFAULT now(),
    closed_at        timestamptz,
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id),
    FOREIGN KEY (child_id, org_id) REFERENCES children(id, org_id),
    FOREIGN KEY (requester_id, org_id) REFERENCES users(id, org_id),
    FOREIGN KEY (assignee_id, org_id) REFERENCES users(id, org_id),
    UNIQUE (requester_id, client_request_id),
    UNIQUE (id, org_id)
);
CREATE INDEX requests_org_status_idx   ON requests (org_id, status);
CREATE INDEX requests_class_time_idx   ON requests (classroom_id, created_at DESC);
CREATE INDEX requests_requester_idx    ON requests (requester_id, created_at DESC);
CREATE INDEX requests_repeat_idx       ON requests (org_id, type, topic_key, created_at)
    WHERE topic_key IS NOT NULL;

-- 학부모 요청 화면 오른쪽 대화
CREATE TABLE request_messages (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id   uuid NOT NULL,
    org_id       uuid NOT NULL,
    sender_type  text NOT NULL CHECK (sender_type IN ('user', 'agent', 'system')),
    sender_id    uuid REFERENCES users(id),   -- 사람일 때만
    body         text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (request_id, org_id) REFERENCES requests(id, org_id)
);
CREATE INDEX request_messages_req_idx ON request_messages (request_id, id);

-- ─────────────────────────────────────────────
-- 3. 자료 창고·문서 조각
-- ─────────────────────────────────────────────

CREATE TABLE documents (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organizations(id),
    classroom_id    uuid,                  -- 없으면 원 전체 자료
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
    uploaded_by     uuid REFERENCES users(id),
    content_sha256  text NOT NULL,
    is_virtual      boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id),
    UNIQUE (org_id, content_sha256),
    UNIQUE (id, org_id),
    CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);

CREATE TABLE document_chunks (
    id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document_id      uuid NOT NULL,
    org_id           uuid NOT NULL,
    chunk_index      integer NOT NULL,
    location         text,                 -- 근거 위치 표시용(예: '2쪽 3항')
    content          text NOT NULL,
    embedding        vector(1024),         -- bge-m3 기준. 모델·차원을 바꾸면 다시 색인
    embedding_model  text,
    created_at       timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (document_id, org_id) REFERENCES documents(id, org_id) ON DELETE CASCADE,
    UNIQUE (document_id, chunk_index)
);
CREATE INDEX document_chunks_embedding_idx ON document_chunks
    USING hnsw (embedding vector_cosine_ops);
CREATE INDEX document_chunks_org_idx ON document_chunks (org_id, document_id);

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
    due_at           timestamptz,          -- 지나면 원장 현황에서 '지연'
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
    CHECK (request_id IS NOT NULL OR subject_id IS NOT NULL)
);
CREATE INDEX cards_inbox_idx   ON cards (org_id, assignee_id, status)
    WHERE status IN ('unassigned', 'pending', 'in_review', 'on_hold');
CREATE INDEX cards_request_idx ON cards (request_id);
CREATE INDEX cards_due_idx     ON cards (org_id, due_at)
    WHERE status IN ('unassigned', 'pending', 'in_review', 'on_hold');

-- 카드가 댄 근거(문서명·위치·적용일을 화면에 보여 줌)
CREATE TABLE card_evidence (
    card_id      uuid NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    chunk_id     bigint NOT NULL REFERENCES document_chunks(id),
    rank         smallint NOT NULL,
    score        real,
    quote        text,
    PRIMARY KEY (card_id, chunk_id)
);

-- 사람의 결정. 카드 판(version)마다 결정은 한 번만 → 재개·승인 버튼을 여러 번 눌러도 한 번만 처리
CREATE TABLE approvals (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    card_id         uuid NOT NULL,
    org_id          uuid NOT NULL,
    card_version    integer NOT NULL,
    decided_by      uuid NOT NULL,
    decision        text NOT NULL CHECK (decision IN ('approve', 'edit_approve', 'reject', 'hold')),
    reason_code     text,                  -- 거절 이유 고르기 값(기억·규칙 제안에 씀)
    reason_text     text,
    edited_content  jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (card_id, org_id) REFERENCES cards(id, org_id),
    FOREIGN KEY (decided_by, org_id) REFERENCES users(id, org_id),
    UNIQUE (card_id, card_version),
    CHECK (decision <> 'reject' OR reason_code IS NOT NULL)
);

-- ─────────────────────────────────────────────
-- 5. 처리 이력(지우지 않고 쌓기만)
-- ─────────────────────────────────────────────

CREATE TABLE events (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id       uuid NOT NULL REFERENCES organizations(id),
    request_id   uuid REFERENCES requests(id),
    card_id      uuid REFERENCES cards(id),
    actor_type   text NOT NULL CHECK (actor_type IN ('user', 'agent', 'system')),
    actor_id     uuid REFERENCES users(id),
    agent_name   text,                     -- 감독·자료·기억·검사 AI 등
    action       text NOT NULL
                 CHECK (action IN ('created', 'classified', 'info_requested', 'assigned',
                                   'reassigned', 'drafted', 'checked', 'returned',
                                   'approved', 'rejected', 'held', 'escalated',
                                   'sent', 'booked', 'completed', 'tool_called',
                                   'tool_failed', 'permission_denied')),
    from_status  text,
    to_status    text,
    detail       jsonb NOT NULL DEFAULT '{}',   -- 비밀값·불필요한 개인정보는 넣지 않음
    created_at   timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX events_request_idx ON events (request_id, id);
CREATE INDEX events_card_idx    ON events (card_id, id);
CREATE INDEX events_org_time_idx ON events (org_id, created_at DESC);

-- ─────────────────────────────────────────────
-- 6. 상담 예약(자산 = 상담실)
-- ─────────────────────────────────────────────

CREATE TABLE rooms (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id     uuid NOT NULL REFERENCES organizations(id),
    name       text NOT NULL,
    is_active  boolean NOT NULL DEFAULT true,
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
    FOREIGN KEY (user_id, org_id) REFERENCES users(id, org_id)
);
CREATE INDEX staff_busy_blocks_idx ON staff_busy_blocks USING gist (user_id, period);

-- 일정 계산 코드가 낸 후보(최대 3개)
CREATE TABLE consultation_slots (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    card_id     uuid NOT NULL REFERENCES cards(id) ON DELETE CASCADE,
    teacher_id  uuid NOT NULL REFERENCES users(id),
    room_id     uuid NOT NULL REFERENCES rooms(id),
    period      tstzrange NOT NULL,
    rank        smallint NOT NULL CHECK (rank BETWEEN 1 AND 3),
    status      text NOT NULL DEFAULT 'proposed'
                CHECK (status IN ('proposed', 'chosen_by_parent', 'confirmed', 'discarded')),
    UNIQUE (card_id, rank)
);

-- 확정된 예약. 같은 상담실·같은 담임이 겹치는 시간은 DB가 저장을 거부함
CREATE TABLE consultation_bookings (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id        uuid NOT NULL,
    request_id    uuid NOT NULL,
    slot_id       bigint REFERENCES consultation_slots(id),
    teacher_id    uuid NOT NULL,
    room_id       uuid NOT NULL,
    period        tstzrange NOT NULL,
    status        text NOT NULL DEFAULT 'confirmed'
                  CHECK (status IN ('confirmed', 'cancelled', 'done')),
    confirmed_by  uuid NOT NULL REFERENCES users(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (request_id, org_id) REFERENCES requests(id, org_id),
    FOREIGN KEY (teacher_id, org_id) REFERENCES users(id, org_id),
    FOREIGN KEY (room_id, org_id) REFERENCES rooms(id, org_id),
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
                    CHECK (kind IN ('rejection_reason', 'preference', 'tone', 'approved_answer')),
    reason_code     text,                  -- 거절 이유면 approvals.reason_code와 같은 값
    content         text NOT NULL,
    structured      jsonb NOT NULL DEFAULT '{}',   -- 예: {"weekday": 3, "before": "14:00"}
    source_card_id  uuid REFERENCES cards(id),
    created_at      timestamptz NOT NULL DEFAULT now(),
    deleted_at      timestamptz,           -- 사용자가 지우면 표시하고 다음 제안에서 뺌
    FOREIGN KEY (owner_id, org_id) REFERENCES users(id, org_id)
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
    proposed_at  timestamptz NOT NULL DEFAULT now(),
    decided_at   timestamptz,
    FOREIGN KEY (owner_id, org_id) REFERENCES users(id, org_id)
);
CREATE UNIQUE INDEX memory_rules_one_open
    ON memory_rules (owner_id, reason_code) WHERE status IN ('proposed', 'active');

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
    author_id     uuid NOT NULL REFERENCES users(id),
    created_at    timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (classroom_id, org_id) REFERENCES classrooms(id, org_id),
    UNIQUE (classroom_id, note_date)
);

-- 아이별 알림장. needs_check 항목이 남으면 보내지 못함
CREATE TABLE daily_notes (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id         uuid NOT NULL,
    input_id       uuid NOT NULL REFERENCES daily_note_inputs(id),
    child_id       uuid NOT NULL,
    note_date      date NOT NULL,
    status         text NOT NULL DEFAULT 'draft'
                   CHECK (status IN ('draft', 'needs_check', 'ready', 'sent')),
    content        jsonb NOT NULL DEFAULT '{}',  -- 하루·식사·투약/귀가 줄·준비물
    open_checks    jsonb NOT NULL DEFAULT '[]',  -- 검사 AI가 짚은 확인 필요 항목
    sent_at        timestamptz,
    FOREIGN KEY (child_id, org_id) REFERENCES children(id, org_id),
    UNIQUE (child_id, note_date),
    CHECK (status <> 'sent' OR jsonb_array_length(open_checks) = 0)
);

-- ─────────────────────────────────────────────
-- 9. 서비스 안 알림
-- ─────────────────────────────────────────────

CREATE TABLE notifications (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id        uuid NOT NULL REFERENCES organizations(id),
    recipient_id  uuid NOT NULL REFERENCES users(id),
    request_id    uuid,
    card_id       uuid,
    kind          text NOT NULL,
    title         text NOT NULL,
    body          text,
    dedupe_key    text NOT NULL UNIQUE,    -- 예: 'card:<id>:approved:<recipient>'. 같은 알림 두 번 안 감
    status        text NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'sent', 'failed', 'held')),
    attempts      smallint NOT NULL DEFAULT 0 CHECK (attempts BETWEEN 0 AND 3),
    last_error    text,
    deliver_after timestamptz NOT NULL DEFAULT now(),   -- 퇴근 뒤 알림 모아 두기(최종)
    created_at    timestamptz NOT NULL DEFAULT now(),
    sent_at       timestamptz,
    read_at       timestamptz
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
    CHECK (passed + errors <= total)
);

-- ─────────────────────────────────────────────
-- 원장 현황(FR-19)은 표를 따로 두지 않고 카드에서 바로 센다
-- ─────────────────────────────────────────────

CREATE VIEW director_overview AS
SELECT
    c.org_id,
    count(*) FILTER (WHERE c.status = 'unassigned')                                AS unassigned,
    count(*) FILTER (WHERE c.status IN ('pending', 'in_review', 'on_hold'))         AS waiting,
    count(*) FILTER (WHERE c.status IN ('pending', 'in_review', 'on_hold')
                       AND c.due_at < now())                                       AS delayed,
    count(*) FILTER (WHERE c.status = 'done'
                       AND c.closed_at >= date_trunc('day', now()))                AS done_today
FROM cards c
GROUP BY c.org_id;
