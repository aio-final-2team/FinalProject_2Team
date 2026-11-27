# 유치온 API 설계 문서 (T13)

보호자 돌봄 메모는 다음에도 같은 설명을 반복하지 않도록 돕는 맞춤 정보예요. 확인 전에는 작성·검사 입력에 쓰지 않고, 확인 뒤에도 사실 근거와 분리해요.

| 항목 | 내용 |
| --- | --- |
| 작업 | T13 API 설계 문서(FastAPI·Function Calling 도구 계약)·모의 API (#170) |
| 작성 · 검토 | 태웅 · 인혜 |
| 계약을 쓰는 쪽 | 화면 T12·T32(성주), 알림장 그래프 T32(프롬프트 검토 영민), 요청 처리 에이전트·자료·근거 검색 T29·T20·T33(영민) |
| 판 | v0.13.8 · 2026-11-27 (판마다 바뀐 내용은 맨 끝 변경 이력 참고. 계약을 바꾸면 예시·모의 응답·시험도 함께 고친다) |
| 2차 검토 링크 | `develop` 브랜치의 [API 설계 문서](https://github.com/aio-final-2team/FinalProject_2Team/blob/develop/Docs/Step2/API_설계_문서.md). API별 상태(2장)는 develop `24258f2` 코드로 판정했다. 이 커밋은 2장 상태 칸의 기준이고, 시연에 쓰는 커밋은 다음 줄에 따로 적는다 |
| 시연 코드 기준 커밋 | 레포 [README](../../README.md#2차-검토-문서)의 '시연 코드 기준 커밋' 한 줄을 본다(11/24 밤 기준 develop `641591f`, 흐름 고치기 #338까지 팀 서버에 배포). 팀 서버를 다시 배포하면 README 그 한 줄만 고친다 |
| 함께 보는 문서 | 아래 기준 판 표의 문서들, T04 흐름·권한 명세 |

| 함께 맞춘 문서 | 기준 판 |
| --- | --- |
| [기획서](../Step1/기획서.md) | 11/23 develop 판(`8f45d51`, #319). 3장 기능 요구사항(FR)과 4장 비기능 요구사항(NFR)의 번호를 쓴다 |
| [입출력 계약표](입출력_계약표_초안.md) | v0.21 · 2026-11-24 |
| [DB 스키마 설계서](DB_스키마_설계서.md) | v0.25 · 2026-11-26, 마이그레이션 0001~0016·0018·0019 |
| OpenAPI 생성물 `contracts/openapi.yaml` | v0.13의 필수 동의 API 53~55·내 정보의 동의 완료 값을 반영했다. 앱이 내는 `/openapi.json`과 같은지는 `test_contract_matches_application`으로 확인한다 |

**1차 검토 뒤 보완.** 1차 검토 뒤에 바뀐 내용과 그 내용을 지키는 시험을 표 하나에 모았다. 시험은 모두 시연 코드 기준 커밋에서 다시 돌려 통과했다. DB 시험과 공유 HTTP 시험은 `tools/test_db.sh`로, 계약 시험은 `tests/integration/api/test_openapi.py`로 돌렸다. 표의 시험 파일은 모두 `tests/integration/`(DB는 `db/`, HTTP는 `api/`) 아래에 있고, `api/` 시험 가운데 `test_openapi.py`를 뺀 나머지는 모의·시험 PG 두 모드에서 모두 돈다. 반영 커밋 칸에는 develop에 합쳐진 커밋을 적었다.

| 바뀐 내용 | 고친 절 | 지키는 시험(파일::함수) | 반영 커밋 |
| --- | --- | --- | --- |
| **접근 차단.** 지금 연결된 아이가 없는 보호자(퇴소 등)는 원 칸 피드에서도 목록·상세·앨범·사진 파일·글 올리기에 모두 403을 받는다. 다른 기관 사용자는 404를, 다른 반 보호자는 반 칸에서 403을 받는다 | [3.29](#329-제안-피드앨범) ⑤, DB 설계서 [4.4](DB_스키마_설계서.md#44-차단-시험) | `api/test_feed.py::test_org_lane_closes_for_guardian_without_linked_child`, `db/test_scope_cases.py::test_unlinked_guardian_loses_child_notes_requests_and_all_feed_photos`, `db/test_scope_cases.py::test_other_class_guardian_is_blocked_on_read_update_and_file`, `db/test_scope_cases.py::test_other_org_user_gets_404_for_document_and_feed_files_with_denial` | [`bf75f8f`](https://github.com/aio-final-2team/FinalProject_2Team/commit/bf75f8f)(코드), [`c80ee67`](https://github.com/aio-final-2team/FinalProject_2Team/commit/c80ee67)(문서) |
| **사진 정리.** 퇴소한 아이의 사진·태그·기억 정리, 파일 삭제가 실패해 남은 파일 정리, 백업 복원 뒤 지운 자료를 다시 닫는 일은 관리 작업으로 한다. API 계약은 바뀌지 않았다 | DB 설계서 [사진·기억의 보존과 삭제](DB_스키마_설계서.md#사진기억의-보존과-삭제) | `api/test_feed.py::test_disk_delete_failure_leaves_only_orphan_file_after_commit`, `db/test_maintenance.py::test_withdraw_dry_run_changes_nothing_then_apply_follows_four_steps`, `db/test_maintenance.py::test_sweep_lists_only_orphans_and_deletes_them_only_with_apply`, `db/test_backup_restore.py::test_dump_restore_revives_later_deletions_until_after_restore_applies_them` | [`bf75f8f`](https://github.com/aio-final-2team/FinalProject_2Team/commit/bf75f8f), [`1d2c228`](https://github.com/aio-final-2team/FinalProject_2Team/commit/1d2c228) |
| **초안 실패 뒤 처리 — 알림장.** 작업 전체가 실패하면 `draft_status = failed`와 `error`로 알리고, 아이 한 명만 실패하면 그 아이에게만 확인 항목 `draft_failed`를 단다. 어느 쪽이든 반 발송은 막힌다. 다시 만들기까지의 복구 이력은 DB 설계서 2.6에 있다 | [3.19.1](#3191-접수부터-결과-조회까지-한-번에-따라가기), [3.26](#326-알림장-다시-만들기--post-apiv1daily-notesdraftsinput_idregenerate), DB 설계서 [2.6](DB_스키마_설계서.md#26-알림장알림평가) | `api/test_daily_notes.py::test_failed_writer_job_is_queryable_without_partial_notes`, `db/test_daily_notes_runner.py::test_one_child_failure_keeps_other_children_and_blocks_batch`, `db/test_daily_note_recovery.py::test_timeout_then_regenerate_is_one_recovered_incident_with_times`, `db/test_daily_note_recovery.py::test_failed_retry_is_handed_off_then_partial_template_is_fallback` | [`c80ee67`](https://github.com/aio-final-2team/FinalProject_2Team/commit/c80ee67), [`bf75f8f`](https://github.com/aio-final-2team/FinalProject_2Team/commit/bf75f8f) |
| **초안 실패 뒤 처리 — 요청 처리 3분 마감.** 3분이 지나면 초안 없는 사람 카드로 넘기고(`ai_timeout`), 처리 중에 예외가 나면 `ai_failed`로 넘긴다. 코드 규칙으로 위험·주제를 다시 저장하고 유효한 담임에게 배정한다. 긴급·판단 필요면 원장 보고와 담임·원장 위험 알림도 남긴다. 모델 응답을 기다리는 동안에는 요청 행 잠금도 DB 연결도 잡지 않는다. 늦게 끝난 결과는 저장 직전에 다시 확인해서 버린다 | [6.1](#61-타임아웃), [6.3](#63-202로-접수하는-작업의-상태-조회) | `db/test_request_lock_timeout.py::test_answer_models_run_outside_request_row_lock`, `db/test_request_lock_timeout.py::test_ai_timeout_hands_off_empty_card_and_drops_late_draft`, `db/test_request_lock_timeout.py::test_timeout_error_raised_by_agent_is_ai_failed` | [`ab58b7c`](https://github.com/aio-final-2team/FinalProject_2Team/commit/ab58b7c) |
| **초안 실패 뒤 처리 — 거절 뒤 재초안.** 담임이 회신 초안을 거절하면 새 회신 카드에는 초안 문장도 검사 결과도 없다. 그래서 그대로 승인하면 409가 나고, 담임이 직접 쓴 글(`edit_approve`)만 나간다 | [3.3](#33-카드-결정--post-apiv1cardscard_iddecisions) '결정마다 바뀌는 것' | `api/test_cards.py::test_reject_redraft_has_no_text_and_needs_teacher_text` | [`ab58b7c`](https://github.com/aio-final-2team/FinalProject_2Team/commit/ab58b7c) |
| 첫 시연 순서, API 목록의 상태 칸(DB 연결·모의만·제안. 보완 당시 52개, 지금 77개) | [2](#2-api-목록), [2.1](#21-첫-시연-흐름의-연결표와-실제-연결-범위) | `api/test_openapi.py::test_all_documented_endpoints_exist`(목록 행이 앱 경로와 같은지) | [`c80ee67`](https://github.com/aio-final-2team/FinalProject_2Team/commit/c80ee67) |
| 요청은 접수됐지만 인계 카드 저장에 실패한 경우 | [5.5.3](#553-사람-인계-카드--create_card), [6.7](#67-대표-사례-대조--화면apidb가-같은-상태로-보이는지) | `db/test_requests.py::test_agent_failure_preserves_request_and_hands_off_without_private_error`, `db/test_requests.py::test_sweep_exact_age_states_card_exclusion_and_concurrent_idempotency` | [`c80ee67`](https://github.com/aio-final-2team/FinalProject_2Team/commit/c80ee67) |
| 기획서·계약표·DB 설계서와 맞춘 기준 판, 생성물이 앱 계약과 같은지 | 위 기준 판 표 | `api/test_openapi.py::test_contract_matches_application` | [`c80ee67`](https://github.com/aio-final-2team/FinalProject_2Team/commit/c80ee67) |

**2차 검토 뒤 보완.** 기준은 `taewoong-fb020-2nd`의 이 PR 최종 HEAD다. 커밋 값은 `git rev-parse HEAD`로 확인하고, 병합 뒤 develop의 시연 커밋으로 맞춘다. 시험 수치의 날짜·범위·명령은 2.2와 DB 설계서 9.2에 적는다.

| 강사 의견 번호 | 바뀐 내용 | 고친 절 | 지키는 시험(또는 확인 기록) | 반영 커밋 |
| --- | --- | --- | --- | --- |
| API 1 | 실제 모델로 알림장 한 반을 담임 입력부터 학부모 수신까지 돌리고 커밋·모델·아이 수·시간·실패 수를 남긴다 | API 3.19.1 ④ 실제 모델 실측 | 팀 서버 2026-11-24 14:45 KST, `tools/rehearse_daily_note.py --remote-ok`(#320). 20명·초안 17초·실패 0 | 이 PR |
| API 2 | 접수·담당 배정 대기·담임 전달 표시를 나누고, 장애 결과는 자동 복구와 사람에게 넘김으로 나눈다 | API 3.2·6.3·6.7·6.8 | `api/test_requests.py::test_unassigned_request_label_changes_after_director_reassign`, `::test_received_request_label_before_agent_runs`, API 6.8의 기존 장애 시험 | 이 PR |
| API 3 | 실제 OpenAPI·목록·계약표·모의 응답을 같은 코드에서 대조하고 MVP·팀 확인 남음을 표시한다 | API 2장·2.2 | `api/test_openapi.py`와 API 2.2 대조표 | 이 PR |
| DB 1 | 백업 뒤 삭제·공개 제한을 재적용하고 공개 전에 목록·앨범·파일을 확인한다 | DB '복원 뒤 서비스 열기 전 확인' | `db/test_backup_restore.py::test_dump_restore_revives_later_deletions_until_after_restore_applies_them` | 이 PR |
| DB 2 | 검사를 통과한 아이별 초안만 복구 성공으로 세고, 사람에게 넘김·재시도 진입 실패를 따로 센다 | DB 2.6 'T58 복구 집계 기준' | `db/test_daily_note_recovery.py`의 현재 집계와 T58 기준 차이 기록, `daily_note_drafted` 저장 코드·0001/0003 DDL 확인 | 이 PR |
| DB 3 | 시험 수치마다 커밋·날짜·alembic 판·범위·명령을 붙이고 권한·마이그레이션을 다시 확인한다 | API 2.2, DB 4.4·6.2·9.2 | `db/test_scope.py`, `db/test_scope_cases.py`, `db/test_migrations.py`, `db/test_feed_migration.py`, `db/test_request_risk_types.py` | 이 PR |

이 문서는 유치온 API 77개(기존 49개는 v0.8 때 develop `24258f2` 코드로 확인, 투약·귀가 취소·수정·알림장 정정 3개와 필수 동의 3개, 기억 확인·승인한 답 고치기 2개, 바쁜 시간 3개·하루 중 기록 3개·알림장 답장과 준비물 확인 2개, 원 일정 1개·개인 알림 시간 2개·교직원 질문 1개·재배정할 선생님 목록 1개·QA 알림장 초기화 1개·사람별 QA 원 도구 3개·사진 3개 추가)와 에이전트 도구 15개의 계약을 담는다. 1~6장은 강사님 'API 설계 문서 작성법'에 나온 '문서에 들어가는 여섯 가지'의 순서를 따르고, 7장에는 API 필드와 DB 컬럼의 대응을, 8장에는 설정값을 적었다. 필드·권한·오류는 입출력 계약표와 같아야 한다. 두 문서가 어긋나면 계약표를 먼저 고친 뒤 두 문서의 판을 함께 올린다. 구현(FastAPI의 `/docs`)과 달라졌을 때도 둘을 대조해 판을 올린다. 모의 API와 생성물 `contracts/openapi.yaml`도 이 문서와 함께 둔다. 모의 API를 쓰는 법과 데모 계정은 [모의 API 안내](../../contracts/mock_api/README.md)에 있다. 제목에 [제안]이 붙은 절은 팀이 아직 계약을 확인하지 않은 내용으로, 투약·귀가(3.27), 상담 지연 입력(3.28), 피드·앨범(3.29), 보낸 알림장 정정(3.30), 필수 동의(3.31), 바쁜 시간(3.32), 하루 중 기록(3.33), 알림장 답장·준비물 확인(3.34), 원 일정(3.35), 개인 알림 시간(3.36), 교직원 AI 질문(3.37), 재배정할 선생님 목록(3.38), 아이 프로필·급식 참고 사진(3.41)이 여기에 해당한다. [QA 전용] 알림장 다시 시험하기(3.39)와 사람별 QA 원 도구(3.40)는 QA 서버에서만 켠다. API별로 지금 어디까지 동작하는지는 2장 표의 상태 칸에 적었다.

**목차.** 1. 공통 정보와 인증 · 2. API 목록 · 3. 엔드포인트 상세 명세 · 4. 검증과 권한 규칙 · 5. Tool 정의와 호출 흐름 · 6. 실행 규칙 · 7. API 필드와 DB 컬럼 대응 · 8. 설정값 · 부록 A. 예시 ID · 부록 B. 강사 가이드 체크리스트 대조 · 변경 이력

## 1. 공통 정보와 인증

### 1.1 서버 주소와 자동 문서

| 항목 | 값 |
| --- | --- |
| 개발 서버 | `http://localhost:8000/api/v1` (`compose.yaml`의 `api` 서비스) |
| 배포 서버 | `https://<배포 도메인>/api/v1` (AWS EC2) |
| 자동 문서 | `http://localhost:8000/docs`, `http://localhost:8000/openapi.json`(버전 접두어 없이 앱 최상위 경로에 있음). 저장소에는 `/openapi.json`에서 뽑아낸 `contracts/openapi.yaml`을 생성물로 둔다 |
| 상태 확인 | `GET /health` (인증 없음, 버전 접두어 없음) |
| 모의 API | API 77개 경로를 제공한다. 원 전체 초기화(72)는 404이며, 모의 업무 데이터는 다시 켜면 초기화된다. 실행 방법·계정·흐름은 [모의 API 안내](../../contracts/mock_api/README.md) 참고 |

### 1.2 인증

| 항목 | 내용 |
| --- | --- |
| 발급 | `POST /api/v1/auth/login`에 `login_id`·`password`를 보내면 서버가 JWT access token을 발급한다. 토큰 수명은 12시간이다. Supabase Auth는 쓰지 않는다(DB 설계서 5.1·5.2) |
| 전달 | `Authorization: Bearer <access_token>` 헤더로 보낸다. Android 앱과 웹이 같은 API를 쓰기 때문에 쿠키는 쓰지 않는다 |
| 검증 | 먼저 서명(`JWT_SECRET`), 만료, 토큰 판(`users.token_version`과 같은지), 계정 사용 여부(`users.is_active`)를 확인한다. 그다음 역할·기관·반을 기준으로 권한을 검사한다(4장) |
| 오류 | 401 `UNAUTHENTICATED`: 토큰이 없거나 만료됐거나, 서명이 틀렸거나, 토큰 판이 낮음 / 403 `FORBIDDEN_ROLE`: 누구인지는 확인됐지만 역할상 할 수 없는 일 / 404 `NOT_FOUND`: 다른 기관·다른 반의 자료(자료가 있다는 사실도 알리지 않음) |

토큰에는 `sub`(계정 ID), `org`(기관 ID), `role`(`parent`·`teacher`·`director`), `ver`(토큰 판), `iat`(발급 시각), `exp`(만료)만 넣는다. 반 소속과 아이 관계는 토큰에 넣지 않고, 요청이 올 때마다 DB에서 확인한다. 그래야 소속이 바뀌어도 토큰을 다시 받지 않아도 된다.

### 1.3 공통 헤더

| 헤더 | 방향 | 내용 |
| --- | --- | --- |
| `Authorization` | 요청 | `Bearer <access_token>`. 로그인과 `/health`를 뺀 모든 요청에 필수 |
| `X-Request-ID` | 요청·응답 | 화면이 요청마다 만들어 보내고, 없으면 서버가 만든다. 서버는 이 값을 응답 헤더로 그대로 돌려주고, 오류의 `trace_id`, 도구 호출, 이력(`events.detail.trace_id`)에도 같은 값으로 남긴다 |
| `Content-Type` | 요청 | `application/json`. 자료와 피드 사진을 올릴 때는 `multipart/form-data` |

가이드 예시에서 추적 ID로 쓰는 `request_id`를 이 서비스에서는 `trace_id`라고 부른다. 이 서비스에서는 `request_id`가 이미 학부모 요청(`requests.id`)을 뜻하기 때문에, 추적 ID까지 같은 이름을 쓰면 둘이 헷갈린다.

### 1.4 공통 오류 형식

모든 API는 아래 한 가지 형식으로 오류를 돌려주며, 오류를 상태 코드 200에 담아 보내지 않는다.

```json
{
  "error": {
    "code": "CARD_VERSION_CONFLICT",
    "message": "다른 사람이 먼저 카드를 처리했어요. 새로고침해 주세요.",
    "trace_id": "6b0f1c2e-9a7d-4c1e-8f3a-2d5b7e9c1a40",
    "details": { "current_version": 3 }
  }
}
```

| HTTP | `code` | 언제 | 누가 검사 |
| --- | --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 | 인증 의존성 |
| 403 | `FORBIDDEN_ROLE` | 역할상 할 수 없는 일(학부모가 카드를 결정하거나 담임이 원장 보고 카드를 결정하는 경우) | 서버 권한 검사 |
| 403 | `FORBIDDEN` | 피드·앨범에서 칸 권한, 사진 범위 변경, 삭제, 숨김이 거부됨(3.29) | 서버 권한 검사 |
| 404 | `NOT_FOUND` | 자료가 없거나, 다른 기관·다른 반·남의 자료임 | 서버 범위 검사 |
| 409 | `CARD_VERSION_CONFLICT` | 화면이 본 카드 판이 현재 판과 다름(`details.current_version`) | 서버 |
| 409 | `ALREADY_DECIDED` | 같은 카드 판에 이미 결정이 있음 | 서버 + DB 유니크 |
| 409 | `INVALID_TRANSITION` | T04 전이 규칙에 없는 상태 변경(예: 회신 전에 처리 완료, 보류 상태가 아닌 카드를 재개) | 서버 |
| 409 | `REASON_REQUIRED` | 학부모가 확인하지 않은 민원을 이유 없이 처리 완료함 | 서버 + DB 트리거 |
| 409 | `SLOT_TAKEN` | 같은 상담실이나 같은 담임에게 겹치는 시간이 이미 확정됐거나, 다른 보호자가 체크 중 | 서버 + DB 배제 제약 |
| 409 | `SLOT_PAST` | 시작 시각이 현재 시각 이하인 후보를 체크하거나 확정함 | 서버 |
| 409 | `SLOT_NOT_CHOSEN` | 학부모가 체크하지 않은 후보로 확정함 | 서버 |
| 409 | `NOTE_BATCH_BLOCKED` | 반에 아직 확인하지 않은 알림장이 있음(`details.blocked[]`) | 서버 |
| 422 | `VALIDATION_FAILED` | 입력 형식·허용 값·길이가 맞지 않거나, 함께 와야 하는 칸끼리 어긋남(`details.fields[]`) | Pydantic |
| 403 | `CONSENT_REQUIRED` | [제안] 현재 약관 판의 필수 동의를 마치지 않고 지정 쓰기 경로를 호출함(3.31) | 서버 |
| 422 | `CONSENT_INCOMPLETE` | [제안] 필수 항목 누락, `details.missing_items[]` | 서버 |
| 409 | `CONSENT_VERSION_MISMATCH` | [제안] 현재 약관 판과 다름, `details.terms_version`에 현재 판 | 서버 |
| 500 | `INTERNAL_ERROR` | 서버 내부 오류. 내부 내용은 응답에 넣지 않고 로그에만 남김 | — |
| 503 | `UPSTREAM_UNAVAILABLE` | 모델·외부 API 장애. 요청은 저장해 두고 나중에 다시 처리 | 서버 |

400은 쓰지 않는다. 필수 정보가 빠진 요청도 오류로 돌려보내지 않고, 정상 응답에 요청 상태 `needs_info`로 담는다. 투약은 교직원이 확인하므로, 빠진 정보를 `received` 상태에서 `missing_fields`로 표시한다(3.27).

FastAPI가 기본으로 내는 422 응답은 예외 처리기에서 위 형식으로 바꿔 돌려준다. `message`는 서버가 넣는 기본 한국어 문장이고, 화면에 띄울 문구는 화면이 `code`별로 따로 정한다.

### 1.5 공통 규칙

| 항목 | 규칙 |
| --- | --- |
| 경로 | 모두 `/api/v1`로 시작한다. 자원 이름은 복수 명사로 쓰고, 실행은 하위 경로에 `POST`로 보낸다(예: `/cards/{card_id}/decisions`). 경로에는 소문자와 하이픈만 쓴다 |
| 목록 | `?page=1&size=20&sort=-created_at` → `{ "items": [...], "total": 37, "page": 1, "size": 20 }`. `size`는 기본 20, 최대 100 |
| 시각 | ISO 8601 형식에 한국 시간 오프셋을 붙인다(`2026-12-01T15:00:00+09:00`). 날짜만 쓸 때는 `YYYY-MM-DD` |
| ID | DB 설계서 2.0의 ID 형식 표를 따른다. 기관·반·계정·아이·요청·카드·문서·상담실·상담 예약·자동 규칙·원에 남은 답·알림장은 UUID 문자열이고, 대화 메시지·문서 조각·결정 기록·이력·상담 후보(`slot_id`)·알림은 정수다 |
| 시간 구간 | DB의 `tstzrange`는 API에서 `{ "start": "...", "end": "..." }`로 주고받는다 |
| 성공 코드 | 조회 200 · AI 처리 접수 202 · 그 밖의 생성 201 · 결정·확정 같은 실행 200 · 삭제 204 |

## 2. API 목록

첫 시연은 알림장 흐름으로 고정한다. 담임이 반 활동과 아이별 메모를 입력하면 AI가 초안을 만들고, 담임이 이를 확인·수정한 뒤 반 전체에 보낸다(기획서 2.3, 결정 D02). 이때 화면은 로그인·내 정보(3.8), 반 아이 목록(3.24), 초안 만들기·진행 상태(3.19), 알림장 보기(3.20), 고치기·확인(3.21), 반 알림장 보내기(3.6) 순서로 API를 부른다. 초안을 만들지 못했거나 다시 써야 하면 다시 만들기(3.26)를 부른다. 알림장을 보내면 학부모는 알림 목록(3.11)에서 `note_sent` 알림을 받고, 알림장 보기(3.20)에서 자기 아이 알림장을 연다.

아래 표에 API 77개(기존 49개는 v0.8 때 develop `24258f2` 코드로 확인, 투약·귀가 취소·수정·알림장 정정 3개와 필수 동의 3개, 기억 확인·승인한 답 고치기 2개, 바쁜 시간 3개·하루 중 기록 3개·알림장 답장과 준비물 확인 2개, 원 일정 1개·개인 알림 시간 2개·교직원 질문 1개·재배정할 선생님 목록 1개·QA 알림장 초기화 1개·사람별 QA 원 도구 3개·사진 3개 추가)를 모았다. 인증·역할 열의 '자기 것'·'우리 반'은 4.2의 범위 규칙을 뜻한다. 상세 열에는 각 API를 자세히 설명한 3장의 절 번호를 적었다. 기존 49개 상태 칸은 develop 코드를 DB 모드(`DATA_BACKEND=db`)로 띄워 호출한 기록이며, 취소·수정 2개는 임시 DB 공용 HTTP 시험으로 확인한다.

| 상태 | 뜻 | 개수 |
| --- | --- | --- |
| DB 연결 | DB 모드에서 실제 표를 읽고 쓴다. 모의 API에도 같은 경로가 있다 | 35 |
| 모의만 | 모의 API에만 있고, DB 모드에서는 501 `NOT_IMPLEMENTED`를 돌려준다 | 0 |
| 제안 | 모의·DB 구현 범위는 상세 절을 따르며, 계약을 팀이 확인하기 전이다(QA 전용 포함) | 39 |

설계서를 실제 동작으로 잇는 단계는 네 가지다(A 화면 계약·B 저장·C 외부 연동·D 모델). 'DB 연결'은 이 가운데 B 저장까지 실제로 확인했다는 뜻이다. 화면과 모델까지 실제로 동작하는지는 첫 시연 흐름을 기준으로 2.1에 따로 적었다. 지금 '모의만' 상태인 API는 없다. 자료 올리기(27)와 자료 상세(29)도 DB에 연결돼 있다. 기존 '제안' 세 절은 모두 기획서의 최종(반드시) 범위에 들어 있지만, 12/08 MVP에는 들어 있지 않다. 아래 표에 기존 세 절과 필수 동의 절의 상태를 적었다.

| 절 | 기획서 요구사항 | MVP(12/08) | 팀 확정 | 구현 |
| --- | --- | --- | --- | --- |
| 3.27 투약·귀가(API 34~36·50~51) | FR-16·AC-09, 최종·중요 | 들어 있지 않음 | 기능은 기획서 2.2에서 확정했고, API 계약은 팀 확인 전이다 | 모의·DB 모두 구현 |
| 3.28 상담 지연 입력(API 37) | FR-17, 최종·중요 | 들어 있지 않음 | 위와 같음 | 모의·DB 모두 구현. 예약 변경과 실제 종료 입력은 후속 |
| 3.29 피드·앨범(API 38~49) | FR-22·AC-06, 최종·중요 | 들어 있지 않음 | 위와 같음 | 모의·DB 모두 구현. DB는 마이그레이션 0010이 필요하다 |
| 3.31 [제안] 필수 동의(API 53~55) | 로그인한 사람의 역할별 전 항목 필수 동의 | 화면 연결 후 확인 | API 계약은 팀 확인 전이다 | 모의·DB 모두 구현, 0016 필요 |
| 3.33 [제안] 하루 중 기록(API 56~58) | FR-10 아이별 관찰과 알림장 메모 | 화면 연결 후 확인 | API 계약은 팀 확인 전이다 | 모의·DB 모두 구현, 0018 필요 |
| 3.32 [제안] 바쁜 시간(API 59~61) | FR-05 상담 후보의 시간 충돌 방지 | 상담 예약의 일정 관리 | API 계약은 팀 확인 전이다 | 모의·DB 모두 구현, 기존 표 사용 |
| 3.34 [제안] 알림장 답장·준비물 확인(API 62·68) | FR-14 학부모 홈 | 최종·중요 | API 계약은 팀 확인 전이다 | 모의·DB 모두 구현, 0019 필요 |
| 3.38 [제안] 재배정할 선생님 목록(API 70) | FR-09·FR-19 원장 재배정 | 화면 연결 후 확인 | API 계약은 팀 확인 전이다 | 모의·DB 모두 구현, 기존 표 사용 |
| 3.39 [QA 전용] 알림장 다시 시험하기(API 71) | QA 반복 시험 도구 | QA 서버 전용 | 운영 사용 금지 | 모의·DB 구현 |
| 3.40 [QA 전용] 사람별 QA 원(API 72~74) | 독립된 QA·오류 진단 | QA 서버 전용 | 운영 사용 금지 | 초기화 DB 전용, 이력·정보 모의·DB 구현 |

| # | 메서드 | 경로 | 인증·역할 | 설명 | 성공 | 요구사항 | 상세 | 상태 | 알림장 MVP | 팀 확인 남음 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | POST | `/api/v1/auth/login` | 없음 | 로그인, 토큰 발급 | 200 | FR-01 | 3.8 | DB 연결 | ○ | — |
| 2 | GET | `/api/v1/me` | JWT | 내 정보·내 아이(학부모)·담당 반(교직원) | 200 | FR-01 | 3.8 | DB 연결 | — | — |
| 3 | POST | `/api/v1/requests` | 학부모 | 요청 만들기(AI 처리 접수) | 202 | FR-02, FR-03 | 3.1 | DB 연결 | — | 영민·성주: 요청 AI·T43 |
| 4 | GET | `/api/v1/requests` | 학부모(자기 것)·담임(우리 반)·원장(기관 전체) | 요청 목록·답변 주체 조회 | 200 | FR-02 | 3.9 | DB 연결 | — | — |
| 5 | GET | `/api/v1/requests/{request_id}` | 학부모(자기 것) · 교직원(우리 반) | 요청 상세·대화·진행 기록 | 200 | FR-02, FR-11 | 3.2, 3.7 | DB 연결 | — | 영민·성주: 요청 AI·T43 |
| 6 | GET | `/api/v1/requests/{request_id}/stream` | 학부모(자기 것) | AI 진행 스트림(SSE) | 200 | NFR-10 | 3.2 | DB 연결 | — | 영민·성주: 요청 AI·T43 |
| 7 | POST | `/api/v1/requests/{request_id}/messages` | 학부모(자기 것) | 대화 이어 쓰기 | 201 | FR-02 | 3.10 | DB 연결 | — | — |
| 8 | POST | `/api/v1/requests/{request_id}/slot-choices` | 학부모(자기 것) | 상담 가능 시간 체크 | 200 | FR-05 | 3.4 | DB 연결 | — | — |
| 9 | POST | `/api/v1/requests/{request_id}/confirm` | 학부모(자기 민원) | 민원 회신 '확인했어요' | 200 | FR-07 | 3.5 | DB 연결 | — | — |
| 10 | GET | `/api/v1/notifications` | JWT(자기 것) | 알림 목록 | 200 | FR-12 | 3.11 | DB 연결 | ○ | 성주: 화면 연결 |
| 11 | POST | `/api/v1/notifications/{notification_id}/read` | JWT(자기 것) | 알림 읽음 | 200 | FR-12 | 3.11 | DB 연결 | — | — |
| 12 | GET | `/api/v1/cards` | 담임·원장 | 받은함(필터 6개·종류 필터·필터별 건수) | 200 | FR-09 | 3.12, 3.7 | DB 연결 | ○ | 영민·성주: 요청 AI·T43 |
| 13 | GET | `/api/v1/cards/{card_id}` | 담임(우리 반)·원장 | 카드 상세(초안·근거·반복 수·이력) | 200 | FR-04, FR-07, FR-09, FR-11 | 3.13, 3.7 | DB 연결 | — | 영민·성주: 요청 AI·T43 |
| 14 | GET | `/api/v1/cards/{card_id}/stream` | 담임(우리 반)·원장 | 카드 AI 진행 스트림(초안 글자 포함) | 200 | NFR-10 | 3.13 | DB 연결 | — | 영민·성주: 요청 AI·T43 |
| 15 | POST | `/api/v1/cards/{card_id}/decisions` | 담임(우리 반)·원장 | 카드 결정(승인·거절·보류·재개·반려·처리 완료·원장님께 올리기) | 200 | FR-05~FR-09 | 3.3 | DB 연결 | — | — |
| 16 | POST | `/api/v1/cards/{card_id}/reclassify` | 담임(우리 반)·원장 | 문의·민원 위험 등급 다시 분류 | 200 | FR-03, FR-07 | 3.14 | DB 연결 | — | — |
| 17 | POST | `/api/v1/cards/{card_id}/bookings` | 담임(우리 반) | 상담 확정 | 200 | FR-05 | 3.4 | DB 연결 | — | — |
| 18 | POST | `/api/v1/cards/{card_id}/instructions` | 원장·원감 | 원장 보고 지시 | 200 | FR-07 | 3.15 | DB 연결 | — | — |
| 19 | POST | `/api/v1/cards/{card_id}/reassign` | 원장·원감 | 담당 재배정 | 200 | FR-09, FR-19 | 3.16 | DB 연결 | — | — |
| 20 | POST | `/api/v1/memory-rules/{rule_id}/decision` | 규칙 주인 | 개인 규칙 제안 켜기·거절 | 200 | FR-06 | 3.17 | DB 연결 | — | — |
| 21 | GET | `/api/v1/overview` | 원장·원감 | 원장 현황(미배정·대기·지연·완료·학부모 미확인 완료) | 200 | FR-09, FR-19 | 3.18 | DB 연결 | — | — |
| 22 | POST | `/api/v1/daily-notes/drafts` | 담임 | 알림장 초안 만들기(AI 처리 접수) | 202 | FR-10 | 3.19 | DB 연결 | ○ | 성주: 화면 연결 |
| 23 | GET | `/api/v1/daily-notes/drafts/{input_id}` | 담임(우리 반) | 알림장 초안 진행 상태 | 200 | FR-10 | 3.19 | DB 연결 | ○ | 성주: 화면 연결 |
| 24 | GET | `/api/v1/daily-notes` | 학부모(내 아이, 보낸 것) · 담임(우리 반) · 원장(같은 기관) | 알림장 보기 | 200 | FR-10 | 3.20, 3.7 | DB 연결 | ○ | 성주: 화면 연결 |
| 25 | PATCH | `/api/v1/daily-notes/{note_id}` | 담임(우리 반) | 알림장 고치기·확인 | 200 | FR-10 | 3.21 | DB 연결 | ○ | 성주: 화면 연결 |
| 26 | POST | `/api/v1/daily-notes/send` | 담임(우리 반) | 반 알림장 한 번에 보내기 | 200 | FR-10 | 3.6 | DB 연결 | ○ | 성주: 화면 연결 |
| 27 | POST | `/api/v1/documents` | 원장·담임 | 자료 올리기(적재 접수) | 202 | FR-13 | 3.22 | DB 연결 | — | — |
| 28 | GET | `/api/v1/documents` | 교직원 | 자료 목록 | 200 | FR-13 | 3.23 | DB 연결 | — | — |
| 29 | GET | `/api/v1/documents/{document_id}` | 교직원 | 자료 상세·적재 상태 | 200 | FR-13 | 3.23 | DB 연결 | — | — |
| 30 | GET | `/api/v1/classrooms/{classroom_id}/children` | 담임(우리 반)·원장(같은 기관) | 반 아이 목록(이름순) | 200 | FR-10 | 3.24 | DB 연결 | ○ | 성주: 화면 연결 |
| 31 | GET | `/api/v1/memories` | 학부모·담임·원장(본인·자기 아이) | 내 AI 기억 보기 | 200 | FR-06 | 3.25 | DB 연결 | — | — |
| 32 | DELETE | `/api/v1/memories/{memory_id}` | 학부모·담임·원장(본인·자기 아이) | 내 AI 기억 지우기 | 204 | FR-06 | 3.25 | DB 연결 | — | — |
| 33 | POST | `/api/v1/daily-notes/drafts/{input_id}/regenerate` | 담임(우리 반) | 미확인 알림장 다시 만들기 | 202 | FR-10 | 3.26 | DB 연결 | — | 성주: 화면 연결 |
| 34 | GET | `/api/v1/children/{child_id}/pickup-guardians` | 자기 아이 보호자·담임·원장 | 등록된 인계자 목록 | 200 | FR-16 | 3.27 | 제안 | — | 팀: 제안 계약 |
| 35 | GET | `/api/v1/care-requests` | 담임·원장 | 교직원용 투약·귀가 요청 목록 | 200 | FR-16 | 3.27 | 제안 | — | 팀: 제안 계약 |
| 36 | POST | `/api/v1/requests/{request_id}/care-decisions` | 담임·원장 | 투약·인계를 실제로 확인·완료·반려 | 200 | FR-16 | 3.27 | 제안 | — | 팀: 제안 계약 |
| 37 | POST | `/api/v1/consultations/{booking_id}/delay` | 그 반 예약 담임 | 상담 예상 종료 기록 | 200 | FR-17 | 3.28 | 제안 | — | 팀: 제안 계약 |
| 38 | GET | `/api/v1/classrooms/{classroom_id}/posts` | 그 반 아이 보호자 | 반 칸 글 목록 | 200 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 39 | POST | `/api/v1/classrooms/{classroom_id}/posts` | 그 반 아이 보호자 | 반 칸 글·사진 올리기 | 201 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 40 | GET | `/api/v1/organizations/{org_id}/posts` | 그 기관 교직원·연결된 아이가 있는 보호자 | 원 칸 글 목록 | 200 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 41 | POST | `/api/v1/organizations/{org_id}/posts` | 그 기관 교직원·연결된 아이가 있는 보호자 | 원 칸 글·사진 올리기 | 201 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 42 | GET | `/api/v1/posts/{post_id}` | 칸 권한 | 글 상세와 볼 수 있는 사진 | 200 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 43 | DELETE | `/api/v1/posts/{post_id}` | 같은 기관 작성자(반 이동·퇴소 뒤에도) | 글·사진 파일 지우기 | 204 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 44 | PATCH | `/api/v1/posts/{post_id}` | 그 기관 원장·원 칸 | 원 칸 글 숨기기 | 200 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 45 | GET | `/api/v1/classrooms/{classroom_id}/albums` | 그 반 아이 보호자 | 반 칸 앨범 | 200 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 46 | GET | `/api/v1/organizations/{org_id}/albums` | 그 기관 교직원·연결된 아이가 있는 보호자 | 원 칸 앨범 | 200 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 47 | GET | `/api/v1/photos/{photo_id}/file` | 칸·사진 권한 | 사진 파일 받기(인증 필요) | 200 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 48 | GET | `/api/v1/children/{child_id}/photo-scope` | 그 아이 보호자 | 현재 사진 공개 범위 | 200 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 49 | PATCH | `/api/v1/children/{child_id}/photo-scope` | 그 아이 보호자 | 사진 공개 범위 바꾸기 | 200 | FR-22·AC-06 | 3.29 | 제안 | — | 팀: 제안 계약 |
| 50 | POST | `/api/v1/requests/{request_id}/cancel` | 학부모(자기 것) | 투약·귀가 요청 취소 | 200 | FR-16 | 3.27 | 제안 | — | 팀: 제안 계약 |
| 51 | PATCH | `/api/v1/requests/{request_id}/care` | 학부모(자기 것) | 투약·귀가 입력 수정 | 200 | FR-16 | 3.27 | 제안 | — | 팀: 제안 계약 |
| 52 | POST | `/api/v1/daily-notes/{note_id}/correct` | 현재 담당 반 담임·같은 기관 원장 | 보낸 알림장 정정 | 200 | FR-10 | 3.30 | 제안 | — | 팀: 제안 계약 |
| 53 | GET | `/api/v1/consents` | 로그인한 사용자 | [제안] 내 필수 동의 조회 | 200 | FR-01 | 3.31 | 제안 | — | 팀: 제안 계약 |
| 54 | POST | `/api/v1/consents` | 로그인한 사용자 | [제안] 전 항목 필수 동의 저장 | 200 | FR-01 | 3.31 | 제안 | — | 팀: 제안 계약 |
| 55 | GET | `/api/v1/classrooms/{classroom_id}/consents` | 같은 기관 원장·현재 담당 반 담임 | [제안] 반 아이별 보호자 동의 현황 | 200 | FR-01 | 3.31 | 제안 | — | 팀: 제안 계약 |
| 56 | GET | `/api/v1/classrooms/{classroom_id}/records` | 그 반 담임·같은 기관 원장 | [제안] 하루 중 기록 조회 | 200 | FR-10 | 3.33 | 제안 | — | 팀: 제안 계약 |
| 57 | POST | `/api/v1/classrooms/{classroom_id}/records` | 그 반 담임 | [제안] 하루 중 기록 등록 | 201 | FR-10 | 3.33 | 제안 | — | 팀: 제안 계약 |
| 58 | DELETE | `/api/v1/records/{record_id}` | 작성 교사·그 반 담임 | [제안] 하루 중 기록 삭제 | 204 | FR-10 | 3.33 | 제안 | — | 팀: 제안 계약 |
| 59 | GET | `/api/v1/staff/busy-blocks` | 본인 교직원·같은 기관 원장 | [제안] 바쁜 시간 조회 | 200 | FR-05 | 3.32 | 제안 | — | 팀: 제안 계약 |
| 60 | POST | `/api/v1/staff/busy-blocks` | 교직원 본인 | [제안] 바쁜 시간 등록 | 201 | FR-05 | 3.32 | 제안 | — | 팀: 제안 계약 |
| 61 | DELETE | `/api/v1/staff/busy-blocks/{id}` | 교직원 본인 | [제안] 바쁜 시간 삭제 | 204 | FR-05 | 3.32 | 제안 | — | 팀: 제안 계약 |
| 62 | POST | `/api/v1/daily-notes/{note_id}/replies` | 그 아이 보호자(보낸 알림장) | [제안] 알림장 답장을 새 문의로 접수 | 202 | FR-14 | 3.34 | 제안 | — | 팀: 제안 계약 |
| 63 | GET | `/api/v1/calendar` | 학부모·담임·원장(자기 기관·볼 수 있는 반) | [제안] 원 일정 조회 | 200 | FR-21 | 3.35 | 제안 | — | 팀: 제안 계약 |
| 64 | GET | `/api/v1/me/notification-settings` | 담임·원장 본인 | [제안] 개인 알림 시간 조회 | 200 | FR-21 | 3.36 | 제안 | — | 팀: 제안 계약 |
| 65 | PATCH | `/api/v1/me/notification-settings` | 담임·원장 본인 | [제안] 개인 알림 시간 저장·해제 | 200 | FR-21 | 3.36 | 제안 | — | 팀: 제안 계약 |
| 66 | POST | `/api/v1/staff/ask` | 담임·원장 | [제안] 원 자료로 교직원 질문에 답변(모델 장애: 503 UPSTREAM_UNAVAILABLE) | 200 | FR-21 | 3.37 | 제안 | — | 팀: 제안 계약 |
| 68 | POST | `/api/v1/daily-notes/{note_id}/supplies-check` | 그 아이 보호자(보낸 알림장) | [제안] 준비물 '챙겼어요' 확인 | 200 | FR-14 | 3.34 | 제안 | — | 팀: 제안 계약 |
| 70 | GET | `/api/v1/staff/teachers` | 원장·원감 | [제안] 재배정할 때 고를 같은 기관 선생님 목록(이름·지금 맡은 반) | 200 | FR-09, FR-19 | 3.38 | 제안 | — | 성주: 재배정 화면 연결 |
| 71 | POST | `/api/v1/qa/daily-notes/reset` | 그 반 담임·원장 (QA 서버만) | [QA 전용] 한 반·날짜 알림장을 초기화해 같은 날 다시 시험 | 200 | QA 도구 | 3.39 | 제안 | QA | QA 서버만 켬 |
| 72 | POST | `/api/v1/qa/sandbox/reset` | 자기 QA 원 사용자 | [QA 전용] 내 원 전체 초기화 | 200 | QA 도구 | 3.40 | 제안 | QA | QA 서버만 켬 |
| 73 | GET | `/api/v1/qa/traces/{trace_id}` | JWT | [QA 전용] 자기 원 요청 이력·500 오류 조회 | 200 | QA 도구 | 3.40 | 제안 | QA | QA 서버만 켬 |
| 74 | GET | `/api/v1/qa/info` | 없음 | [QA 전용] 배포 판·켜진 기능·원 목록 조회 | 200 | QA 도구 | 3.40 | 제안 | QA | QA 서버만 켬 |
| 75 | GET | `/api/v1/children/{child_id}/profile-photo` | 학부모(내 아이)·담임(우리 반)·원장(같은 기관) | [제안] 아이 프로필 사진 파일 | 200 | FR-10, FR-23 | 3.41 | 제안 | — | 화면: 아이 동그라미 |
| 76 | GET | `/api/v1/meal-photos` | JWT(같은 기관) | [제안] 기간 안 급식 참고 사진 목록 | 200 | FR-11 | 3.41 | 제안 | — | 화면: 식단 사진 |
| 77 | GET | `/api/v1/meal-photos/{meal_date}/file` | JWT(같은 기관) | [제안] 급식 참고 사진 파일 | 200 | FR-11 | 3.41 | 제안 | — | 화면: 식단 사진 |

| 67 | POST | `/api/v1/memories/{memory_id}/confirm` | 그 아이 보호자 | 돌봄 메모 기억·버림 | 200 | FR-20 | 3.25 | DB 연결 | — | 화면 연결 필요 |
| 69 | PATCH | `/api/v1/saved-answers/{answer_id}` | 승인한 담임·같은 기관 원장 | 승인 답 끄기·켜기 | 200 | FR-20 | 3.25 | DB 연결 | — | 화면 연결 필요 |

알림장 MVP의 ○는 `origin/taewoong-fb020-rehearsal:tools/rehearse_daily_note.py`의 실제 호출이다. `/me`·알림 읽음·다시 만들기는 그 리허설이 부르지 않아 ○를 붙이지 않는다. 팀 확인 남음은 코드 기본값(`LLM_MODEL_SUPERVISOR` 비움, `ANSWER_WRITER=stub`, `DAILY_NOTE_WRITER=app.modules.daily_notes.stub_writer:write`)과 WBS T43(할일), 2.1의 화면 미확인 범위를 뜻한다. 권한 밖 문의의 고정 안내는 DB·모의 두 모드에서 학부모 대화에 바로 남긴다(3.1·5.7). 이 표시가 API 미구현이나 팀 서버의 현재 스위치 값을 뜻하지는 않는다.

SSE 두 개(6번·14번)는 실시간 진행 화면(NFR-10)에서 쓴다. 투약·귀가 요청의 SSE는 AI 단계를 거치지 않고 현재 상태 done으로 바로 끝난다(3.27).

### 2.1 첫 시연 흐름의 연결표와 실제 연결 범위

알림장 흐름 하나를 요구사항부터 시험까지 한 줄로 이었다. 화면은 T12 화면 지도의 웹 경로다. 시험 이름 뒤에 (DB)가 붙으면 DB 모드에서만, (모의)가 붙으면 모의 모드에서만 돌고, 아무 표시가 없으면 두 모드에서 모두 돈다.

| 단계 | 요구사항 | 화면 | API | 도구 | DB | 시험 |
| --- | --- | --- | --- | --- | --- | --- |
| 반 입력·초안 | FR-10, AC-04 | `/teacher/notes` | 3.24, 3.19 | 5.5.1, 5.5.2 | `daily_note_inputs`, `daily_notes`, 이력 `daily_note_drafted` | `test_draft_preserves_inputs_requests_sources_and_duplicate`, `test_classroom_children_sorted_complete_and_director_allowed`(모의), `test_one_child_failure_keeps_other_children_and_blocks_batch`(DB) |
| 확인·수정 | FR-10, FR-08 | `/teacher/notes/:noteId` | 3.20, 3.21 | — | `daily_notes.status`·`open_checks`·`confirmed_at`, 이력 `daily_note_edited`·`daily_note_confirmed` | `test_first_original_survives_edits_confirm_send_and_events_link_only_the_note`, `test_empty_patch_unconfirms_ready_note`(모의) |
| 발송 잠금·보내기 | FR-10, FR-12, AC-04 | `/teacher/notes` | 3.6 | — | `daily_notes.sent_at`, `notifications`(`note_sent`), 이력 `daily_note_sent` | `test_batch_atomic_patch_and_parent_visibility`, `test_unfinished_batch_cannot_send` |
| 다시 만들기 | FR-10 | 웹에 아직 없음 | 3.26 | 5.5.1, 5.5.2 | `daily_notes.ai_original`, 반 묶음 카드 `draft.regenerated_by` | `test_regenerate_preserves_edited_notes_and_ready_including_check_ids`, `test_regenerate_recovers_failed_or_stopped_input` |
| 학부모 보기 | FR-10, FR-12 | `/parent/home`(알림 목록 화면은 아직 없음) | 3.20, 3.11 | — | `daily_notes`(`sent`만), `notifications` | `test_batch_atomic_patch_and_parent_visibility` |

어느 부품까지 실제로 연결했는지는 아래와 같다.

| 단계 | 연결할 것 | 지금 상태 | 근거 |
| --- | --- | --- | --- |
| A 화면 계약 | 웹 화면 ↔ API | 화면으로 확인함(11/27). 확인·고치기·발송 잠금·반 발송·학부모 홈을 웹 화면에서 끝까지 눌러 봤다. 초안 만들기는 메모 17개를 손으로 넣지 않으려고 같은 API로 보내서, 화면의 진행 표시와 '관찰 기록'은 아직 화면으로 보지 않았다 | FB-021-1(`49edbe5`, 별빛반 20명, 담임 `teacher01`·학부모 `parent01`) |
| B 저장 | API ↔ 시험 DB | 실제로 확인함 | 49개를 DB 모드로 불러 501이 없음, `tools/test_db.sh`의 DB 시험 290개 통과(과거 기준: 2026-11-23, `24258f2`, 0010, `tools/test_db.sh`; 이번 결과는 2.2) |
| C 외부 연동 | 외부 API | 해당 없음. 알림장 흐름은 외부 API를 부르지 않는다 | — |
| D 모델 | 그래프 ↔ 모델 ↔ 저장 | 실제 연동 확인함(11/27). 팀 서버 `DAILY_NOTE_WRITER=graph`·`RUN_IN=worker`, gpt-6-luna로 20명 초안 16초, 확인 필요 4명(민감 3·다른 아이 1). 코드 기본 작성기는 여전히 모델을 부르지 않는 대역이다 | FB-021-1(`49edbe5`). 단위 시험: `tests/unit/test_daily_note_graph.py` 27개 통과(과거 기준: 2026-11-23, `24258f2`, 0010 호환·DB 미사용, `python -m pytest tests/unit/test_daily_note_graph.py`; 이번 결과는 2.2) |

**재현과 증빙.** 검토자는 아래 조건으로 같은 결과를 다시 볼 수 있다.

| 칸 | 내용 |
| --- | --- |
| 기준 커밋 | develop `24258f2` |
| 환경 | 시험용 PostgreSQL 16 + pgvector(`pgvector/pgvector:pg16`)에 마이그레이션 0001~0010과 데모 시드를 넣고 `DATA_BACKEND=db`로 띄운다. 작성기는 기본값(대역)이다. 모의 모드는 `DATA_BACKEND=mock`이다 |
| 실행 명령 | `tools/test_db.sh`(시험용 DB를 띄워 DB 시험과 모의 HTTP 시험을 돌린 뒤 컨테이너를 지운다), `python -m pytest tests/unit/test_daily_note_graph.py tests/integration/api/test_openapi.py` |
| 결과 | 과거 기록(2026-11-23, `24258f2`, 0010; 위 명령·범위): DB 290개, 모의 HTTP 670개, 그래프 단위 27개, OpenAPI 2개 통과. 이번 판의 결과는 2.2 |
| 화면 링크 | 아직 없다. 첫 시연 점검 때 붙인다 |

| 남은 일 | 담당 | 다음 확인 |
| --- | --- | --- |
| 웹 화면에서 세 상태(진행 중·완료·실패)와 발송 잠금 표시 확인(A) | T32 성주 | T32 일정(11/30~12/02) |
| 실제 모델로 알림장 초안 만들기(D) | T32 성주, 프롬프트 검토 영민 | T32 일정 |
| 모의 API가 진행 중(`queued`·`running`) 응답을 내게 하기. 지금은 접수하면서 바로 끝나서 진행 중 화면은 DB 모드에서만 볼 수 있다 | T13 태웅 | 화면 점검 전 |
| 웹의 다시 만들기 버튼과 학부모 알림 목록 화면 | T32 성주 | T32 일정 |

### 2.2 2차 계약 대조와 시험 기준

이번 검증은 2026-11-24, 이 PR 최종 HEAD(`taewoong-fb020-2nd`), alembic head `0011` 기준이다. 팀 서버의 배포 커밋은 README를 따르며, 이 로컬 검증과 섞지 않는다. 모의 시험에서 DB 사례가 건너뛰어지는 것은 전용 PG 주소가 없기 때문이다. 두 모드의 공유 HTTP 시험은 `tools/test_db.sh`에서 모두 실행한다. 아래 명령은 레포 루트에서 실행한다. 로컬 기록이며 CI 실행 URL은 없다.

| 대조 대상·범위 | 명령·시험 | 결과 |
| --- | --- | --- |
| 실제 `/openapi.json` ↔ `app.openapi()` ↔ `contracts/openapi.yaml`, 2장 목록 | `DATA_BACKEND=mock .venv/bin/python -m pytest -q tests/integration/api/test_openapi.py -p no:cacheprovider` | 2개 통과 |
| 계약표 v0.20 ↔ API v0.11 ↔ 모의·DB 공유 HTTP | `tools/test_db.sh -p no:cacheprovider` | 343개 통과; 공유 HTTP 726개 통과(mock·시험 PG 두 모드) |
| 모의 전체(단위·HTTP·계약, 실제 모델·외부 API 미사용) | `DATA_BACKEND=mock .venv/bin/python -m pytest -q tests -p no:cacheprovider` | 810개 통과·702개 건너뜀(전용 PG 미지정) |
| 가짜 모델 알림장 그래프 단위 시험 | `DATA_BACKEND=mock .venv/bin/python -m pytest -q tests/unit/test_daily_note_graph.py -p no:cacheprovider` | 27개 통과 |
| 코드 정적 검사 | `.venv/bin/python -m ruff check apps agents tests tools` | 오류 없음 |

| 1차 표 뒤 대표 응답 변경 | 문서·계약표 | 지키는 시험 |
| --- | --- | --- |
| #324: 메시지 `sender_role`(학부모 글·교사 답 구분) | API 3.2·3.10·7장, 계약표 2.1(v0.19.1부터) | `api/test_requests.py::test_additional_message_is_stored_with_trace_without_leaking_draft`, `api/test_cards.py::test_reply_approval_confirmation_completion_and_event_order` |
| #326: 문의·상담 `risk_level`·`risk_category`(학부모 응답에서는 숨김) | API 3.14·5.7·6.5·6.6, DB 0011, 계약표 4.1(v0.19부터) | `db/test_request_risk_types.py::test_risky_inquiry_skips_answer_model_and_saves_risk`; 공유 HTTP는 `api/test_complaints.py` |
| 이 PR: 요청 표시가 담당 유무를 반영함. JSON 키·타입은 같음 | API 3.2·6.7, 계약표 2.1(v0.20) | `api/test_requests.py::test_unassigned_request_label_changes_after_director_reassign`, `::test_received_request_label_before_agent_runs`, `::test_parent_labels_follow_assignment_and_keep_type_branches` |

자동 대조 범위는 OpenAPI와 API 목록, HTTP 응답 스키마다. 계약표는 2.1·2.2·4.1을 코드와 직접 대조했다. `sender_role`과 위험 등급 확대는 이미 현재 브랜치에 들어 있어 대표 응답을 다시 고칠 필요가 없고, 이번 표시 규칙만 v0.20에 더한다. 실제 모델·웹 화면·팀 서버 복원은 이 시험의 증명 범위에 들지 않는다.

## 3. 엔드포인트 상세 명세

API 77개를 가이드의 여덟 칸으로 쓴다. 필드 표의 '빈값'은 그 필드가 `""`이나 `null`을 받아도 되는지를 뜻한다. 예시의 고정 ID는 부록 A의 데모 ID이고, 3.8 이후 예시는 주요 응답 필드와 목록 첫 항목만 남겨 줄여 보인다. 토큰과 새로 발급한 ID도 `…`로 줄인다. 경로의 `{card_id}`·`{input_id}`·`{note_id}`에는 앞선 응답에서 받은 값을 넣는다.

### 3.1 요청 만들기 — `POST /api/v1/requests`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모가 안내 문의·상담·민원을 보낸다. 서버는 요청을 저장하고 바로 202를 돌려준다. 감독 AI 분류부터 카드 생성까지는 그 뒤에 따로 처리한다(FR-02, FR-03) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json` |
| ③ 경로·쿼리 | 없음 |
| ④ 요청 본문 | 아래 필드 표 |
| ⑤ 검증·권한 | 형식은 Pydantic이 검사한다(422). 역할이 학부모가 아니면 403, `child_id`가 내 아이(`child_guardians`)가 아니면 404다. `previous_request_id`는 내 요청이면서 끝난 상태(`completed`·`rejected`)여야 한다. 내 요청이 아니면 404, 아직 끝나지 않았으면 409 `INVALID_TRANSITION`이다 |
| ⑥ 정상 응답 | 202 + 요청 ID·상태·스트림 주소. 같은 `client_request_id`로 다시 보내면 200 + 처음 만든 요청 |
| ⑦ 오류 응답 | 아래 오류 표 |
| ⑧ 실행 규칙 | 요청을 저장만 하고 바로 답한다(10초 안). 같은 제출이 두 번 오면 `(requester_id, client_request_id)` DB 유니크 제약이 막는다. AI 처리가 실패해도 요청은 남고, 재시도 뒤에도 실패하면 사람 카드로 넘긴다(6.3). 투약·귀가는 AI를 실행하지 않고 교직원 목록에 남긴다(3.27). 위험하지 않은 권한 밖 문의는 고정 안내 메시지를 남기고 카드 없이 `sent_or_booked`로 바뀐다. 아이 안전·갈등·건강 주제나 우리 아이에 관한 글은 담임 흐름을 유지한다(5.7) |

**요청 본문 필드**

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `client_request_id` | 본문 | string | 필수 | 불가 | 8~64자, 화면이 만든 UUID 권장 | 같은 제출을 두 번 받지 않기 위한 키 |
| `type` | 본문 | string | 필수 | 불가 | `inquiry`·`consultation`·`complaint`·`medication`·`pickup` | 요청 유형. 투약·귀가는 3.27 |
| `body` | 본문 | string | 필수 | 불가 | 1~2,000자 | 질문·요청 내용 |
| `child_id` | 본문 | string(UUID) | 필수 | 불가 | 내 아이 | 대상 아이. 반은 서버가 아이 정보로 정한다 |
| `previous_request_id` | 본문 | string(UUID) | 선택 | `null` 가능 | 내 요청, 끝난 상태 | 끝난 요청을 다시 열 때 넣는 이전 요청 |
| `pickup_guardian_id` | 본문 | string(UUID) | 선택 | null 가능 | pickup만, 같은 아이의 등록된 활성 보호자 | 미등록 인계자일 때는 생략한다(3.27) |
| `pickup_name`·`pickup_relation` | 본문 | string | 선택 | null·빈값 가능 | pickup만, 각 100자 이하 | 미등록 인계자의 이름·관계다. 추측해서 채우지 않는다. |
| `medication_name`·`medication_dose`·`medication_time` | 본문 | string | 선택 | null·빈값 가능 | medication만, 각 100자 이하 | 약 이름·용량·시간이다. 빠진 항목은 missing_fields로 표시한다. |

```http
POST /api/v1/requests
Authorization: Bearer <JWT>
X-Request-ID: 6b0f1c2e-9a7d-4c1e-8f3a-2d5b7e9c1a40
Content-Type: application/json

{
  "client_request_id": "c1a7e0d2-5b3f-4e8a-9c61-0f2d4b6a8e10",
  "type": "complaint",
  "body": "등원 버스가 이번 주에만 세 번 20분씩 늦었어요.",
  "child_id": "00000000-0000-4000-8000-000000000501",
  "previous_request_id": null
}
```

```http
HTTP/1.1 202 Accepted
X-Request-ID: 6b0f1c2e-9a7d-4c1e-8f3a-2d5b7e9c1a40

{
  "request": {
    "id": "00000000-0000-4000-8000-000000000702",
    "status": "received",
    "stream_url": "/api/v1/requests/00000000-0000-4000-8000-000000000702/stream"
  }
}
```

**정상 응답 필드**

| 필드 | 타입 | 항상 | 설명 |
| --- | --- | --- | --- |
| `request.id` | string(UUID) | 예 | 요청 ID |
| `request.status` | string | 예 | 처음엔 `received`. 같은 키로 다시 보냈다면(200) 지금 상태 |
| `request.stream_url` | string | 예 | AI 진행 스트림 주소(3.2) |

**오류**

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 문제 |
| 403 | `FORBIDDEN_ROLE` | 교직원이 호출 |
| 404 | `NOT_FOUND` | `child_id`가 내 아이가 아님, `previous_request_id`가 내 요청이 아님 |
| 409 | `INVALID_TRANSITION` | `previous_request_id`가 아직 끝나지 않은 요청 |
| 422 | `VALIDATION_FAILED` | 허용 밖 `type`, `body` 길이 초과, 필수 칸 없음 |

### 3.2 요청 상세·스트림 — `GET /api/v1/requests/{request_id}`, `GET …/stream`

투약·귀가 요청도 다른 요청처럼 자기 요청 목록·상세·대화·스트림에서 읽는다. 다만 실제 확인·완료와 등록 인계자 계약은 3.27에 따로 있고, 투약·귀가 요청에 민원용 confirm을 부르면 409다.

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모가 자기 요청의 상태·대화·진행 기록·상담 후보를 본다. 교직원도 카드 화면에서 같은 요청을 본다(FR-02, FR-11). AI 처리 단계는 스트림으로 실시간 확인한다(NFR-10) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`. 스트림 요청에는 `Accept: text/event-stream`을 붙인다. 토큰을 헤더로 보내야 해서 `EventSource` 대신 `fetch` 스트림으로 읽는다 |
| ③ 경로·쿼리 | `request_id`(경로, UUID, 필수) |
| ④ 요청 본문 | 없음 |
| ⑤ 검증·권한 | 학부모는 자기 요청만, 담임은 우리 반 요청(대체 담임은 기간 안)과 재배정받은 카드의 요청만, 원장은 원 전체를 본다. 범위 밖이면 404 |
| ⑥ 정상 응답 | 200. 학부모 응답에는 위험 등급·보류 이유·도구 호출·처리한 교직원을 넣지 않고, 처리 이력도 학부모용 요약만 준다. 반려 이유와 답변 출처는 학부모에게도 준다(3.7) |
| ⑦ 오류 응답 | 401, 404, 422(UUID 형식이 아님) |
| ⑧ 실행 규칙 | 조회라서 재시도해도 된다. 스트림이 끊기면 상세를 다시 불러 상태를 맞추고 나서 다시 연결한다 |

```json
{
  "request": {
    "id": "00000000-0000-4000-8000-000000000701",
    "type": "consultation",
    "title": "아이 친구 관계 상담",
    "status": "needs_info",
    "status_label": "시간을 골라 주세요",
    "missing_fields": [],
    "hold_until": null,
    "parent_confirmed_at": null,
    "created_at": "2026-12-01T09:10:00+09:00",
    "updated_at": "2026-12-01T09:10:20+09:00"
  },
  "messages": [
    { "id": 41, "sender_type": "user", "sender_role": "parent", "body": "아이 친구 관계로 상담하고 싶어요.", "created_at": "2026-12-01T09:10:00+09:00" }
  ],
  "timeline": [
    { "label": "접수됨", "at": "2026-12-01T09:10:00+09:00" },
    { "label": "시간을 골라 주세요", "at": "2026-12-01T09:10:20+09:00" }
  ],
  "consultation": {
    "slots": [
      { "id": 9001, "period": { "start": "2026-12-02T15:00:00+09:00", "end": "2026-12-02T15:30:00+09:00" }, "room": "상담실", "status": "proposed" },
      { "id": 9002, "period": { "start": "2026-12-02T16:00:00+09:00", "end": "2026-12-02T16:30:00+09:00" }, "room": "상담실", "status": "proposed" },
      { "id": 9003, "period": { "start": "2026-12-03T15:00:00+09:00", "end": "2026-12-03T15:30:00+09:00" }, "room": "상담실", "status": "proposed" }
    ],
    "booking": null
  }
}
```

| 필드 | 타입 | 항상 | 설명 |
| --- | --- | --- | --- |
| `request.status` | string | 예 | 기획서 6장 공통 상태 11개 중 하나 |
| `request.status_label` | string | 예 | 서버가 역할·상태·담당 유무를 반영한 표시 이름을 준다. 화면은 이 값을 쓴다 |
| `request.missing_fields[]` | string[] | 예 | `needs_info`일 때 학부모에게 물어볼 항목이다. 투약은 received 상태에서도 빠진 약 이름·용량·시간을 표시한다(3.27). 없으면 빈 목록이다. |
| `request.hold_until` | date | 아니오 | 보류 예정일. 보류 이유는 학부모에게 주지 않음 |
| `request.parent_confirmed_at` | datetime | 아니오 | 민원 '확인했어요' 시각 |
| `messages[]` | 목록 | 예 | 대화. `sender_type`은 `user`(사람)·`agent`(AI)·`system`. 권한 밖 고정 안내는 `agent`·`sender_role=null`이며 담임이 승인한 답과 구분한다(5.7) |
| `messages[].sender_role` | string | 아니오 | 메시지를 쓴 사람의 역할(`parent`·`teacher`·`director`). AI나 시스템이 쓴 글이면 null이다. 학부모 글과 담임이 승인해 보낸 답은 `sender_type`이 둘 다 `user`여서, 화면에서는 이 값으로 말풍선을 나눈다 |
| `timeline[]` | 목록 | 예 | 학부모용은 상태가 바뀐 단계만 표시 이름으로 보임 |
| `consultation` | 객체 | 아니오 | 상담 요청일 때만. 후보 최대 3개와 확정 예약 |

**학부모 표시와 담당 배정.** 화면은 서버 `status_label`을 쓰며 상태 이름만으로 문구를 만들지 않는다. 요청 목록·상세·타임라인은 현재 요청의 `assignee_id`를 같은 기준으로 읽는다. 담당자 ID는 학부모 응답에 더하지 않는다. 타임라인 문구도 현재 담당에 맞춰 계산하므로 과거 담당자 배정의 감사 기록으로 쓰지 않는다.

| 요청 상태·조건 | 학부모 표시 |
| --- | --- |
| `received` | 접수됨 |
| `classified` | 접수됨 |
| `assigned`(담임 배정 뒤) | 선생님께 전달됨 |
| `assigned`·`awaiting_review`·`on_hold`, `assignee_id`가 비어 있음 | 담당 선생님 배정 중 |
| `awaiting_review`, 담당 있음 | 선생님 확인 중 |
| `on_hold`, 담당 있음 | 확인이 늦어지고 있어요 |
| 민원 `sent_or_booked`, `parent_confirmed_at` 있음 | 확인함 · 선생님이 마무리하고 있어요 |

민원의 확인 여부는 목록·상세·타임라인에 함께 반영한다. 요청 상태는 `sent_or_booked` 그대로이며, 담임이 처리 완료하면 "완료"로 표시한다. 타임라인의 회신 단계도 현재 확인 여부를 읽는다.

투약·귀가의 '선생님 확인 대기/완료'와 '투약/인계 완료', 상담의 '시간을 골라 주세요/예약 확정' 분기는 그대로다. 원장 재배정 뒤 요청에 담당자가 생기면 원래 상태의 표시로 돌아간다. 공용 HTTP 시험 `test_unassigned_request_label_changes_after_director_reassign`은 담임 없는 반→카드 `unassigned`→목록·상세의 배정 대기→원장 재배정→선생님 확인 중을 두 모드에서 확인한다. 접수 직후는 `test_received_request_label_before_agent_runs`, 유형별 문구는 `test_parent_labels_follow_assignment_and_keep_type_branches`로 확인한다(실행 기준 2.2).

**스트림 이벤트**: `stage`(`classifying`·`searching`·`drafting`·`checking`) · `done`(`request_status`) · `error`(1.4 형식). 학부모 스트림에는 답변 글자(`token`)와 카드(`card`)를 보내지 않는다. 담임이 승인하기 전의 초안이 학부모에게 나가면 안 되기 때문이다.

```text
event: stage
data: {"stage": "classifying", "at": "2026-12-01T09:10:01+09:00"}

event: done
data: {"request_status": "needs_info"}
```

### 3.3 카드 결정 — `POST /api/v1/cards/{card_id}/decisions`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임·원장이 받은함 카드에 결정을 내린다. AI가 만든 초안은 이 결정을 거쳐야만 학부모에게 나간다(FR-05~FR-09, NFR-03) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json` |
| ③ 경로·쿼리 | `card_id`(경로, UUID, 필수) |
| ④ 요청 본문 | 아래 필드 표. 화면에서 본 카드의 `version`을 꼭 함께 보낸다 |
| ⑤ 검증·권한 | 형식과 함께 와야 하는 칸은 Pydantic이 본다(422). 역할·범위·카드 종류(403·404)와 판·전이·학부모 확인(409)은 서버가 본다 |
| ⑥ 정상 응답 | 200 + 바뀐 카드·요청 상태. 다음 카드가 생기면 `next_card_id` |
| ⑦ 오류 응답 | 아래 오류 표 |
| ⑧ 실행 규칙 | 카드 판 하나에는 결정이 하나만 저장된다(`approvals (card_id, card_version)` 유니크). 그래서 같은 판으로 다시 보내면 409 `ALREADY_DECIDED`가 나고, 두 번 처리되지 않는다. 응답이 끊겼다면 카드 상세로 상태를 확인한 뒤 다시 보낸다 |

**요청 본문 필드**

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `version` | 본문 | integer | 필수 | 불가 | 1 이상 | 화면에서 본 카드 판 |
| `decision` | 본문 | string | 필수 | 불가 | `approve`·`edit_approve`·`reject`·`hold`·`resume`·`dismiss`·`complete`·`escalate`·`acknowledge` | 결정. 원장 지시(`instruct`)는 18번 API |
| `reason_code` | 본문 | string | `reject`·`dismiss`면 필수 | 불가 | 이유 코드 8개(4.1) | 거절·반려 이유 |
| `reason_text` | 본문 | string | `hold`·`reason_code = other`면 필수, `complete`이고 학부모가 아직 확인하지 않았으면 필수 | 불가 | 1~500자 | 보류 이유·기타 이유·마무리한 방법 |
| `hold_until` | 본문 | date | `hold`면 필수 | 불가 | 내일부터(오늘 날짜는 422) | 보류 예정일 |
| `edited_content` | 본문 | object | `edit_approve`면 필수 | 불가 | 초안과 같은 모양 | 담임이 고친 내용 |

```http
POST /api/v1/cards/00000000-0000-4000-8000-000000000802/decisions
Authorization: Bearer <JWT>
X-Request-ID: 0e7d4a51-2c3b-4f6e-9a18-5b7c9d0e1f23

{
  "version": 2,
  "decision": "complete",
  "reason_text": "전화로 설명드리고 마무리함"
}
```

```json
{
  "card": { "id": "00000000-0000-4000-8000-000000000802", "status": "done", "version": 3 },
  "request": { "id": "00000000-0000-4000-8000-000000000702", "status": "completed" },
  "next_card_id": null
}
```

**결정마다 바뀌는 것**

| `decision` | 카드 | 요청 | 이력(`events.action`) | 알림 |
| --- | --- | --- | --- | --- |
| `approve`·`edit_approve` | `approved` → 발송 뒤 `done` | `approved` → `sent_or_booked` | `approved`, `sent` | 학부모 `sent_or_booked` |
| `reject` | `rejected`, 같은 요청에 새 초안 카드가 생김. 회신 카드(`reply_draft`)를 거절했다면 새 카드에는 초안 문장도 검사 결과도 없다. 그래서 그대로 `approve`하면 409 `INVALID_TRANSITION`이 나고, 담임이 직접 쓴 글을 `edit_approve`로 보내야 한다 | `awaiting_review` → `assigned`, 새 초안이 나오면 다시 `awaiting_review` | `rejected` | 없음(이유는 기억 AI의 재료로 씀) |
| `hold` | `on_hold` + `hold_until` | `on_hold`(상담 원장 보고는 그대로) | `held` | 학부모 `on_hold`(예정일만; 상담 원장 보고는 없음) |
| `resume` | `pending` | `on_hold` → `awaiting_review`(상담 원장 보고는 그대로) | `resumed` | 없음 |
| `dismiss` | `rejected`, 상담이면 체크한 후보도 `discarded` | `rejected` | `dismissed` | 학부모 `rejected` |
| `complete` | `done` | `sent_or_booked` → `completed`(민원만) | `completed` | 학부모 `completed` |
| `escalate` | 원장 보고 카드(`director_report`)가 새로 생김 | `escalated` | `escalated` | 원장 `director_report` |

상담 원장 보고 카드에서는 원장만 `acknowledge`(확인)·`hold`·`resume`를 쓴다. 확인은 `pending`·`in_review`·`on_hold` 카드만 `done`으로 닫고 `report_acknowledged` 이력을 남긴다. 보류·수동 재개·자동 재개도 그 카드만 바꾸고 요청 상태·학부모 표시·알림·체크는 그대로 둔다. 이 결정들도 `approvals`에 저장한다(`acknowledge`는 0014 마이그레이션). 다른 종류 카드의 `acknowledge`는 409 `INVALID_TRANSITION`이다.

**오류**

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 403 | `FORBIDDEN_ROLE` | 학부모가 호출, 담임이 원장 보고 카드에 결정 |
| 404 | `NOT_FOUND` | 다른 기관·다른 반 카드 |
| 409 | `CARD_VERSION_CONFLICT` | `version`이 지금 판과 다름(`details.current_version`) |
| 409 | `ALREADY_DECIDED` | 같은 판에 이미 결정이 있음 |
| 409 | `INVALID_TRANSITION` | 민원이 아닌데 `complete`, 회신 전 `complete`, 보류가 아닌데 `resume` |
| 409 | `REASON_REQUIRED` | 학부모가 '확인했어요'를 안 눌렀는데 `reason_text` 없이 `complete` |
| 422 | `VALIDATION_FAILED` | 허용 밖 `decision`·`reason_code`, `reject`인데 `reason_code` 없음, `hold`인데 `hold_until` 없음 |

`REASON_REQUIRED`는 422가 아니라 409다. 학부모가 확인했는지는 DB를 봐야 알 수 있는 조건이어서, 본문 형식만 보는 Pydantic 검사(422)와 섞지 않는다.

### 3.4 상담 시간 체크·확정 — `POST …/requests/{request_id}/slot-choices`, `POST …/cards/{card_id}/bookings`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모가 후보 1~3개 중 가능한 시간을 체크하면(`slot-choices`), 담임이 그중 하나로 확정한다(`bookings`). 확정하기 전에는 예약이 아니다(FR-05) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장) |
| ③ 경로·쿼리 | `request_id` 또는 `card_id`(경로, UUID, 필수) |
| ④ 요청 본문 | 아래 필드 표 |
| ⑤ 검증·권한 | 체크는 요청한 학부모만, 확정은 그 상담 후보 카드의 담당 교사만 할 수 있다(다른 반에서 재배정받은 교사도 가능, 원장은 대신 확정하지 않음). 범위 밖이면 404, 역할이 다르면 403 |
| ⑥ 정상 응답 | 체크: 200 + 후보 상태, 요청은 `awaiting_review`. 확정: 200 + 예약 |
| ⑦ 오류 응답 | 아래 오류 표 |
| ⑧ 실행 규칙 | 체크한 시간은 다른 요청의 확정 예약·유효 체크와 겹치면 안 된다. 이미 시작한 후보는 체크하든 확정하든 409 `SLOT_PAST`다. 체크 만료와 보류·원장 지시 때의 처리는 아래 규칙을 따른다 |

체크할 때 상담실이나 담임의 시간이 다른 요청의 확정 예약 또는 24시간 안의 체크와 겹치면 409 `SLOT_TAKEN`이다.
24시간이 지난 체크는 요청이 `awaiting_review`일 때만 풀고 `needs_info`로 돌린다. 이때 담임에게 `slot_hold_expired` 알림을 남긴다.
보류나 원장 보고 중에는 체크와 요청 상태를 그대로 두고, 재개되거나 원장이 지시한 뒤에 만료를 검사한다.
긴급·판단 필요 상담에는 원장 보고 카드가 함께 생기지만 요청은 `escalated`가 되지 않는다(5.7). 원장은 별도 `acknowledge`로 보고만 확인할 수 있고(3.3), 지시는 `escalated`인 요청만 받는다. 담임이 예약을 확정하거나 상담을 반려(`dismiss`)할 때 같은 요청의 열린 원장 보고 카드도 함께 닫는다. 이때 알림을 더 보내지는 않는다. 판단 필요(`uncertain`)로 결정을 막는 규칙은 재분류로 풀 수 있는 문의·민원에만 쓰고, 상담은 판단 필요여도 담임이 그대로 확정·반려한다.
`escalated`에서는 원장이 지시하기 전에 확정할 수 없다. 원장이 지시하면 보고 카드를 닫고 상담 후보 카드로 돌려보낸다.
최종 확정은 담임 → 상담실 순서로 거는 자문 잠금과 DB 배제 제약으로 한 건만 받는다(DB 설계서 9.1 F1-7).
확정하면 학부모에게 `consultation_booked` 알림을 한 번 남긴다. 제목은 "상담 예약 확정", 본문은 예약한 한국 날짜·시간(`YYYY-MM-DD HH:MM~HH:MM`)이다. 문의·민원 회신 알림은 기존 `sent_or_booked`("답변 도착")를 쓴다.

`none_fit`은 기존 후보를 버리고 희망 시간과 겹치는 빈 후보를 먼저, 겹침이 없으면 시간 거리가 가까운 순으로 최대 3개 다시 제안한다. `preferred_times`의 명시 날짜(YYYY-MM-DD), 오늘·내일·모레·다음 주·요일, HH:MM·오전/오후 시각·범위·이후/이전·오전/오후를 코드가 읽고, 해석하지 못한 문장은 원문을 이력에 보존한 채 빠른 시간 순서를 쓴다. 담임(없으면 원장)에게 원문을 담은 `parent_message` 알림을 남긴다. 다음 재제안·재배정에도 마지막 희망 시간을 반영한다.
담임 없는 반은 `unassigned` 상담 카드의 생성 때 원장에게 `new_card`를 보낸다. 후보가 있으면 학부모 체크를 허용하고, 후보가 없으면 원장 재배정으로 새 담당 기준 후보를 계산한다.
확정 순간 충돌은 해당 후보만 `discarded`, 나머지 후보·체크는 보존하고 새 회차 후보를 최대 3개 더 만든다. 카드 판을 1 올리고 요청을 `needs_info`로 돌려 `slot_conflict_reproposed`(detail.slot_id·new_slot_ids)와 학부모 `needs_info` 알림을 같은 트랜잭션에 저장한다. 그 뒤 409 `SLOT_TAKEN`을 반환하므로 요청·카드를 새로 읽고 다시 선택한다. 충돌 때 승인·예약은 만들지 않는다. 재체크는 살아 있는 이전 후보도 받으며 최종 체크 목록을 교체한다. 알림 저장 실패는 재제안도 함께 롤백한다.

**필드**

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `slot_ids[]` | 체크 본문 | integer[] | `none_fit`이 아니면 필수 | 불가 | 1~3개, 그 카드의 살아 있는 후보(충돌 뒤 보존된 후보 포함) | 가능한 시간 |
| `none_fit` | 체크 본문 | boolean | 선택 | — | 기본 `false` | 맞는 시간이 없음 → 후보를 다시 계산 |
| `preferred_times` | 체크 본문 | string | `none_fit`이면 필수 | 불가 | 1~200자 | 원하는 시간 설명 |
| `version` | 확정 본문 | integer | 필수 | 불가 | 1 이상 | 상담 후보 카드 판 |
| `slot_id` | 확정 본문 | integer | 필수 | 불가 | 학부모가 체크한 후보 | 확정할 시간 |
| `booking.id` | 확정 응답 | string(UUID) | 항상 | 불가 | — | 예약 ID |
| `booking.room` | 확정 응답 | string | 항상 | 불가 | — | 상담실 이름 |
| `booking.period` | 확정 응답 | object | 항상 | 불가 | `start` < `end` | 상담 시간 |

```http
POST /api/v1/requests/00000000-0000-4000-8000-000000000701/slot-choices
{ "slot_ids": [9001, 9003] }

HTTP/1.1 200 OK
{ "slots": [ { "id": 9001, "status": "chosen_by_parent" }, { "id": 9003, "status": "chosen_by_parent" } ],
  "request": { "id": "00000000-0000-4000-8000-000000000701", "status": "awaiting_review" } }
```

```http
POST /api/v1/cards/00000000-0000-4000-8000-000000000801/bookings
{ "version": 1, "slot_id": 9001 }

HTTP/1.1 200 OK
{ "booking": { "id": "00000000-0000-4000-8000-000000000901", "room": "상담실",
               "period": { "start": "2026-12-02T15:00:00+09:00", "end": "2026-12-02T15:30:00+09:00" } },
  "request": { "id": "00000000-0000-4000-8000-000000000701", "status": "sent_or_booked" } }
```

**오류**

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 403 | `FORBIDDEN_ROLE` | 교직원이 체크, 학부모·원장·카드 담당이 아닌 교사가 확정 |
| 404 | `NOT_FOUND` | 남의 요청, 다른 반 카드, 그 요청의 후보가 아닌 `slot_id` |
| 409 | `INVALID_TRANSITION` | 시간을 고를 단계(`needs_info`)가 아닌데 체크, 원장 보고 중 지시 전에 확정 |
| 409 | `SLOT_NOT_CHOSEN` | 학부모가 체크하지 않은 후보로 확정 |
| 409 | `SLOT_TAKEN` | 체크 때 다른 확정·유효 체크와 겹침. 확정 때 예약과 겹치면 충돌 후보만 버리고 재제안·알림까지 저장한 뒤 409 |
| 409 | `SLOT_PAST` | 시작 시각이 현재 시각 이하인 후보를 체크·확정 |
| 409 | `CARD_VERSION_CONFLICT` | 확정할 때 카드 판이 다름 |
| 422 | `VALIDATION_FAILED` | `slot_ids` 0개·4개 이상, `none_fit`인데 `preferred_times` 없음 |

### 3.5 민원 '확인했어요' — `POST /api/v1/requests/{request_id}/confirm`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모가 민원 회신을 읽고 '확인했어요'를 누른다. 그러면 담임 받은함의 '확인 필요'로 올라가고, 이제 담임이 처리 완료를 누를 차례가 된다(FR-07) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장) |
| ③ 경로·쿼리 | `request_id`(경로, UUID, 필수) |
| ④ 요청 본문 | 없음 |
| ⑤ 검증·권한 | 요청한 학부모만 누를 수 있다. 민원이 아니거나 아직 회신 전(`sent_or_booked`가 아님)이면 409 |
| ⑥ 정상 응답 | 200 + `request { status, parent_confirmed_at }`. 상태는 `sent_or_booked` 그대로 |
| ⑦ 오류 응답 | 401, 403(교직원), 404(남의 요청), 409 `INVALID_TRANSITION`(민원 아님·회신 전) |
| ⑧ 실행 규칙 | 다시 눌러도 처음 시각을 그대로 두고 200을 돌려준다(멱등). 담임에게 가는 `parent_confirmed` 알림도 한 번만 보낸다(`dedupe_key`) |

```json
{ "request": { "id": "00000000-0000-4000-8000-000000000702", "status": "sent_or_booked",
               "parent_confirmed_at": "2026-12-01T19:02:00+09:00" } }
```

### 3.6 알림장 보내기 — `POST /api/v1/daily-notes/send`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임이 그날 반 알림장을 한 번에 보낸다. 아이 한 명이라도 확인이 안 끝났으면 아무것도 보내지 않는다(FR-10) |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json` |
| ③ 경로·쿼리 | 없음 |
| ④ 요청 본문 | `classroom_id`(UUID, 필수, 우리 반), `note_date`(date, 필수, 오늘 또는 지난날) |
| ⑤ 검증·권한 | 그 반 담임만 보낼 수 있다(대체 담임은 기간 안). 원장은 보내지 않는다 |
| ⑥ 정상 응답 | 200 + `sent_count`. 아이마다 `daily_notes.status = sent`가 되고, 학부모에게 `note_sent` 알림이 간다 |
| ⑦ 오류 응답 | 403, 404, 409 `NOTE_BATCH_BLOCKED`(`details.blocked[] { note_id, child_id, open_checks[] }`), 422. 초안 작업이 queued·running·failed 상태여도 409 `NOTE_BATCH_BLOCKED`이고, 이때는 `details.blocked=[]`다. |
| ⑧ 실행 규칙 | 한 트랜잭션 안에서 반 전체를 잠그고 확인한 뒤 보낸다. 이미 보낸 알림장은 다시 보내지 않고, `sent_count`에서도 뺀다 |

```json
{ "error": { "code": "NOTE_BATCH_BLOCKED", "message": "확인이 안 끝난 알림장이 있어요.",
             "trace_id": "…", "details": { "blocked": [ { "note_id": "…", "child_id": "00000000-0000-4000-8000-000000000502",
             "open_checks": [ { "id": "c1", "item_key": "supplies", "kind": "date_check", "problem": "준비물 날짜가 식단표와 달라요", "sentence": "내일 실내화" } ] } ] } } }
```

초안 뒤 반에 들어온 아이처럼 알림장 자체가 없는 아이도 발송을 막는다. 이때 `details.blocked[]`의 해당 항목은 `{ note_id: null, child_id, status: "missing", open_checks: [] }`다. 기존 알림장 미확인 항목은 기존 `{ note_id, child_id, open_checks }` 모양을 유지한다. 반의 모든 아이 알림장이 `sent`이면 묶음 카드를 `done`으로 닫고, 같은 발송을 반복해도 카드 판·학부모 알림을 늘리지 않는다.

### 3.7 화면이 쓰는 조회 응답 칸

T12 화면 지도에 나온 화면들이 조회 응답에서 쓰는 칸을 여기에 모았다. 계약표 2장에도 같은 이름으로 실려 있다. 모두 서버가 조회할 때 채우는 칸이라 DB에 새로 더하는 칸은 없다.

**로그인·내 정보** (`POST /auth/login`, `GET /me`)

| 필드 | 타입 | 누구 | 설명 | DB |
| --- | --- | --- | --- | --- |
| `user.classroom_ids[]` | string[](UUID) | 담임 | 오늘 볼 수 있는 반. 대체 담임은 기간 안에 드는 반만, 원장·원감·학부모는 빈 목록 | `classroom_staff`(`valid_from`~`valid_to`) |
| `children[] { id, display_name, classroom_id }` | 목록 | 학부모 | 내 아이 | `child_guardians` → `children` |

**받은함 목록** (`GET /api/v1/cards`)

쿼리 파라미터는 아래 표와 같다. 화면의 종류 필터(전체·민원·상담·문의)는 카드 종류(`kind`)가 아니라 요청 유형(`request_type`)으로 받고, 상태 필터와 함께 적용한다. 긴급 건은 따로 필터를 두지 않고 '확인 필요' 맨 위에 올린다. `risk_level=urgent`는 API 조회 조건으로만 남긴다. `kind`는 `reply_draft`·`director_report` 같은 카드 종류를 가리켜서 화면에서 말하는 '종류'와 뜻이 다르기 때문이다.

| 파라미터 | 타입 | 필수 | 값 | 설명 |
| --- | --- | --- | --- | --- |
| `filter` | string | 선택 | `unassigned`·`needs_review`·`uncertain`·`on_hold`·`in_progress`·`done` | 받은함 필터 6개(분류 규칙은 3.12). 주지 않으면 끝나지 않은 카드 전부 |
| `request_type` | string | 선택 | `complaint`·`consultation`·`inquiry`·`all` | 종류 필터의 '민원·상담·문의'. `all`이거나 주지 않으면 '전체' |
| `risk_level` | string | 선택 | `urgent` | 긴급 카드만 조회. 화면 종류 필터에는 없음 |
| `kind` | string | 선택 | 카드 종류 6개 | 카드 종류로 거를 때(원장 보고만 보기 등) |
| `assignee` | string | 선택 | `me` | 내 담당만 |
| `page`·`size` | integer | 선택 | 기본 1·20, `size` 최대 100 | 목록 규칙(1.5) |

응답에는 건수를 두 가지 함께 준다. 상태 필터와 종류 필터가 한 화면(T12 T-01)에 같이 걸려서, 칩마다 숫자를 붙이려면 둘 다 있어야 하기 때문이다. `counts {}`는 상태 필터 6개의 건수로, `request_type`·`risk_level`을 주면 그 조건 안에서 센다. 반대로 `type_counts { all, complaint, consultation, inquiry }`는 종류별 건수이고, `filter`를 주면 그 상태 필터 안에서 센다. 필터와 건수는 모두 서버가 계산한다.

| 화면용 필드(`items[]`) | 타입 | 언제 | 설명 | DB |
| --- | --- | --- | --- | --- |
| `request_id` | string(UUID) | 요청이 있는 카드 | 알림장 묶음·규칙 제안 카드는 `null` | `cards.request_id` |
| `child_id`·`child_name`·`requester_name` | UUID·string·string 또는 null | 요청이 있는 카드 | 요청의 아이·보호자 현재 표시 이름이에요. 요청이 없으면 세 칸 모두 null, 아이가 없으면 아이 두 칸은 null이에요. 목록은 조인해서 한꺼번에 읽어요 | `requests.child_id` → `children.display_name`, `requests.requester_id` → `users.display_name` |
| `risk_category` | string | 긴급 요청만 | 긴급 사유 4가지(`child_safety`·`staff_attack`·`legal_external`·`privacy_leak`) | `requests.risk_category` |
| `repeat_count` | integer | 민원만 | 같은 반에서 최근 30일 안에 들어온 같은 주제 민원 수. `topic_key = other`면 `null` | 조회 때 셈(`requests_repeat_idx`) |
| `check { passed, issue_count }` | 객체 | 검사가 끝난 카드 | 검사 AI 결과 요약. 검사를 못 했으면 `null` | `cards.check_result` |
| `note_batch { input_id, draft_status, children[] }` | 객체 또는 null | 알림장 묶음 카드 | 현재 반 아이 전체와 `missing`을 포함한 상태 | `daily_note_inputs`·`children`·`daily_notes` 조회 |
| `parent_choice_count` | integer | 상담 후보 카드 | 학부모가 체크한 시간 수(지금 회차) | `consultation_slots`(`status = chosen_by_parent`) 개수 |
| `classroom { id, name }` | 객체 | 항상 | 반 이름. 원장 화면에서 반을 구분하려고 준다. 반이 없는 규칙 제안 카드는 null이다 | `requests.classroom_id` → `classrooms.name` |

알림장 묶음 카드(`daily_note_batch`)는 목록의 `items[].note_batch`와 상세의 `card.note_batch`에 `{ input_id, draft_status, children[] }`를 준다. `children[]`은 현재 같은 기관·반의 아이마다 `{ child_id, display_name, note_id, status }`다. 알림장이 없는 아이도 `note_id = null`, `status = "missing"`으로 포함한다. 실제 알림장 상태는 `draft`·`needs_check`·`ready`·`sent`이고, 다른 종류 카드는 `note_batch = null`이다. 초안 뒤에 들어온 아이를 숨기지 않기 위한 조회 값이며, 가짜 알림장 행을 저장하지 않는다.

목록의 `status_label`과 알림장 상세의 `card.status_label`은 초안 작업이 `queued`·`running`이면 "만드는 중", `failed`면 "만들기 실패 · 다시 만들기", 전원 템플릿(`all_children_template`)인 미완료 카드는 "AI가 못 만들었어요 · 직접 쓰거나 다시 만들기", 그 밖에 성공한 미완료 카드는 "확인 필요", 발송 완료 카드는 "완료"다. 다른 종류 카드의 상세 `card.status_label`은 null이다. 작업의 원래 상태는 `note_batch.draft_status`로도 구분한다.

**카드 상세** (`GET /api/v1/cards/{card_id}`)

| 화면용 필드 | 타입 | 언제 | 설명 | DB |
| --- | --- | --- | --- | --- |
| `request.child_id`·`request.child_name`·`request.requester_name` | UUID·string·string 또는 null | 요청이 있는 카드 | 목록과 같은 아이·보호자 이름이에요. `StaffRequest`를 쓰는 재분류 응답에도 함께 나가요. 요청이 없으면 request 자체가 null이에요 | 위 목록 규칙과 같음 |
| `messages[] { id, sender_type, sender_role, body, created_at }` | 목록 | 항상(요청 없으면 빈 목록) | 해당 요청의 전체 대화를 메시지 ID 오름차순으로 준다. 사람의 역할은 `parent`·`teacher`·`director`, AI·시스템 역할은 null이다. 카드의 기관·반·담당 권한을 먼저 검사한다 | `request_messages` → `users.role` |
| `card.note_batch`·`card.status_label` | 객체·string 또는 null | 알림장 묶음 카드 | 목록과 같은 반 아이별 상태·초안 진행/실패 표시 | 위 목록 규칙과 같음 |
| `card.summary` | string | AI가 만든 카드 | AI 요약(`create_card`의 `summary`) | `cards.draft->>'summary'` |
| `card.draft.risk_reason` | string 또는 없음 | 판단 필요 요청의 카드 | 감독 AI가 쓴 판단 필요 이유 한 줄(최대 80자, 민감정보 가림). 화면은 값이 없으면 기본 문구를 쓴다. 마이그레이션 없이 회신·원장 보고·상담 후보 카드 초안에 남긴다 | `cards.draft->>'risk_reason'` |
| `card.check_result { passed, issues, attempt }` | 객체 또는 null | 검사 결과가 있을 때 | passed는 boolean, attempt는 검사 횟수(integer), issues는 아래 모양의 목록이며 없으면 []. 요청 백엔드는 그래프가 준 검사 결과와 부가 칸(memory_unavailable 등)을 그대로 저장한다 | `cards.check_result` |
| `card.check_result.issues[] { field, problem }` | object[] | 검사 지적이 있을 때 | field는 검사 항목(string: 출처·날짜·대상·누락·민감정보), problem은 사람이 읽는 설명(string). 예: `[{"field":"출처","problem":"자료 답변을 확인하지 못했어요."}]` | `cards.check_result->'issues'` |
| `evidence[].is_current` | boolean | 근거가 있을 때 | 근거 문서가 지금 판이면 참. 옛 판(`superseded`)이거나 충돌 확인 대기(`conflict_pending`)이거나 적용 기간이 지난 문서면 거짓. 초안 근거의 같은 chunk_id는 저장 전에 첫 인용·점수만 남기고 순서대로 rank를 매긴다 | `documents.status`·`effective_to` |
| `warnings[]` | string[] | 항상(없으면 빈 목록) | 화면 경고. `stale_evidence`(옛 판 근거가 있음) · `no_evidence`(근거 없음) · `law_unchecked`(법령 확인 못 함) · `check_unavailable`(검사 못 함) · `notify_failed`(교직원 알림을 못 만듦) | `evidence[].is_current`, 자료 AI 결과(`cards.draft`), `cards.check_result` |
| `parent_choices[] { slot_id, period, room, chosen_at, hold_expires_at }` | 목록 | 상담 후보 카드 | 학부모가 체크한 시간. `hold_expires_at` = `chosen_at` + 24시간 | `consultation_slots`(`chosen_by_parent`) |
| `rule { id, reason_code, rule_text, status }` | 객체 | `kind = rule_proposal` | 개인 규칙 제안 내용. 켜기·거절은 20번 API | `cards.subject_id` → `memory_rules` |
| `director_instruction { text, by, at }` | 객체 | 원장 지시가 있는 담임 카드 | 원장 지시 메모 | 같은 요청에 딸린 원장 보고 카드에 남은 `approvals`(`decision = instruct`)의 `reason_text`·`decided_by`·`created_at` |

**요청 상세(학부모)** (`GET /api/v1/requests/{request_id}`, 3.2 응답의 칸)

| 화면용 필드 | 타입 | 언제 | 설명 | DB |
| --- | --- | --- | --- | --- |
| `consultation.slots[] { id, period, room, status }` | 목록 | 상담 요청 | 후보 시각과 장소(3.2와 같음). MVP에서는 상담실 대면 한 가지뿐이라 방식(대면·화상) 칸은 두지 않고, 화상상담(FR-18)을 넣을 때 `mode`를 더한다 | `consultation_slots`, `rooms.name` |
| `request.hold_until` | date | 보류 중 | 보류 예정일(3.2와 같음). 이유는 주지 않음 | `cards.hold_until` |
| `rejection { reason_code, reason_text }` | 객체 | 반려된 요청 | 반려 이유. T04 2장의 학부모 표시 문구 '처리할 수 없는 요청이에요 (이유)'에 들어간다. 담임이 반려할 때는 이 글이 학부모에게 보인다는 안내를 담임 화면에 띄워야 한다 | `approvals`(`decision = dismiss`) |
| `sources[] { document_title, location, effective_from }` | 목록 | 회신이 나간 문의·민원 | 답변 출처. 학부모에게 공개된 문서(`visibility`가 `parents`·`all`)만. 법령(`doc_type = law`) 근거는 담임이 승인한 답변 글에 그 법령 이름이 실제로 들어 있을 때만 나간다(담임 카드에는 항상 보임) | 승인된 카드의 `card_evidence` → `document_chunks` → `documents` |

**알림장** (`GET /api/v1/daily-notes`의 `content`, `open_checks[]`)

목록의 각 알림장은 `input_id`(UUID, 필수)를 함께 준다. 원래 담임 입력 묶음(`daily_note_inputs.id`)이므로 화면은 별도 POST 없이 작업 상태 조회·재생성 주소에 쓸 수 있다. 같은 묶음의 아이들은 같은 input_id를 가지며 날짜·반이 다른 묶음과는 구분된다. 이 칸은 목록에만 추가하며 알림장 PATCH 응답은 기존 모양을 유지한다.

`daily_notes.content`(`jsonb`)의 모양을 정한다. 줄마다 값과 출처가 따로 들어 있어서 화면은 둘을 함께 보여 줄 수 있다.

```json
{
  "items": [
    { "key": "day", "label": "오늘 하루", "value": "블록 놀이와 바깥 산책을 했어요.", "source": { "type": "teacher_input" } },
    { "key": "meal", "label": "식사", "value": "점심 카레라이스를 다 먹었어요.",
      "source": { "type": "document", "document_id": "…", "document_title": "12월 식단표" } },
    { "key": "supplies", "label": "준비물", "value": "내일 실내화", "source": { "type": "teacher_input" } }
  ]
}
```

| 필드 | 값 | 설명 |
| --- | --- | --- |
| `items[].key` | `day`·`meal`·`medication`·`pickup`·`supplies`·`child`·`inquiry` | 줄 종류. `child`는 아이별 메모를 풀어 쓴 줄로 출처는 `teacher_input`이며, 메모가 없거나 공백뿐이면 이 줄도 없다. 보호자 문의는 반 공통 `day`와 따로 `inquiry` 줄로, 투약·귀가는 `medication`·`pickup` 줄로 잇고, 이 줄들의 출처는 `request`다. 투약·귀가를 실제로 확인하는 일은 3.27에서 다루고, 현재 상태는 응답의 request_status로 보여 준다 |
| `items[].source.type` | `teacher_input`·`document`·`request` | 순서대로 담임 입력(`daily_note_inputs`), 원 자료(식단·일정), 학부모 요청(문의·투약·귀가) |
| `items[].source.document_id`·`document_title` | — | `document`일 때 |
| `items[].source.request_id` | — | `request`일 때 |
| `open_checks[] { id, item_key, kind, problem, sentence, request_id? }` | — | 확인할 항목. `id`·`item_key`·`kind`·`problem`은 필수이고, 그중 `problem`은 선생님이 읽는 설명이다. `sentence`는 문제가 걸린 초안 문장이며 없으면 null이다. `request_id`는 선택 칸(UUID)이라 생략하거나 null로 둘 수 있고, 보호자 요청 누락일 때 해당 요청 ID를 넣는다. `resolved_checks[]`에는 `id`만 보낸다 |
| `open_checks[].kind` | `not_in_memo`·`sensitive`·`other_child`·`date_check`·`absent`·`draft_failed`·`check_failed`·`request_missed`·`return_limit` | 순서대로 메모에 없음·민감 정보·다른 아이·날짜 확인·결석·아이 초안 실패·검사 실패·보호자 요청 누락·AI 수정 한도 초과 |

`return_limit`의 `problem` 예시는 "AI가 두 번 고쳐도 남은 문제가 있어요. 직접 확인해 주세요"다. 다른 확인 항목과 함께 해결해야 `ready`로 확인하고 발송할 수 있다. 그래프가 백엔드에서 아직 지원하지 않는 문자열 종류를 주면 백엔드는 초안을 보존하고 그 항목의 `kind`만 `check_failed`로 바꾼다. 원래 종류 이름은 로그에만 남기고 `problem`에 붙이지 않는다. 나머지 형식·출처 검증은 그대로 적용하며 `end`·`handoff_reason`은 저장하지 않는다.

학부모가 받는 알림장(`sent`)의 `open_checks`는 늘 빈 목록이다(DB 제약).

### 3.8 로그인·내 정보 — `POST /api/v1/auth/login`, `GET /api/v1/me`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 로그인으로 토큰을 받고, 내 정보에서 현재 계정·담당 반·아이를 확인한다(FR-01). |
| ② 요청 헤더 | 로그인은 `Content-Type: application/json`, 내 정보는 `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 없음. |
| ④ 요청 본문 | 로그인만 `login_id`·`password`를 받고, 내 정보는 본문이 없다. |
| ⑤ 검증·권한 | 로그인은 계정·비밀번호·사용 여부를, 내 정보는 JWT 서명·만료·토큰 판·기관·역할·사용 여부를 확인한다. |
| ⑥ 정상 응답 | 200. 로그인은 `access_token`·`token_type`·`user`·`children`, 내 정보는 `user`·`children`. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | JWT는 HS256을 쓰고 기본 수명은 12시간이며, `iat`도 넣는다. 반·아이 관계는 조회할 때 다시 구한다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `login_id` | 로그인 본문 | string | 필수 | 불가 | 1~64자 | 데모 계정은 모의 API README 참고 |
| `password` | 로그인 본문 | string | 필수 | 불가 | 1~128자 | 데모 전용 비밀번호는 `demo1234` |
| `access_token`·`token_type` | 로그인 응답 | string | 항상 | 불가 | JWT·`bearer` | 다음 요청의 인증에 사용 |
| `user` | 응답 | object | 항상 | 불가 | `id`·`role`·`display_name`·`org_id`·`classroom_ids[]` | 역할은 `parent`·`teacher`·`director` |
| `user.consents_complete` | 응답 | boolean | 항상 | 불가 | 현재 약관 판의 전 항목 완료 여부 | [제안] 동의 화면 진입 판단, 로그인·내 정보 모두 포함 |
| `user.classroom_ids[]`·`children[]` | 응답 | 목록 | 항상 | 빈 목록 가능 | 역할별 값·아이 객체 모양은 3.7 참고 | 담임은 반, 학부모는 아이; 나머지는 빈 목록 |

```http
POST /api/v1/auth/login
{"login_id": "parent01", "password": "demo1234"}
HTTP/1.1 200 OK
{"user": {"id": "00000000-0000-4000-8000-000000000401", "role": "parent", "display_name": "하늘이 보호자", "org_id": "00000000-0000-4000-8000-000000000001", "classroom_ids": [], "consents_complete": true}, "children": [{"id": "00000000-0000-4000-8000-000000000501", "display_name": "하늘", "classroom_id": "00000000-0000-4000-8000-000000000101"}], "access_token": "…", "token_type": "bearer"}
GET /api/v1/me
HTTP/1.1 200 OK
{"user": {"id": "00000000-0000-4000-8000-000000000401", "role": "parent", "display_name": "하늘이 보호자", "org_id": "00000000-0000-4000-8000-000000000001", "classroom_ids": [], "consents_complete": true}, "children": [{"id": "00000000-0000-4000-8000-000000000501", "display_name": "하늘", "classroom_id": "00000000-0000-4000-8000-000000000101"}]}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 로그인 실패·비활성 계정, 내 정보의 토큰 문제 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.9 요청 목록 — `GET /api/v1/requests`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모는 자기 요청과 다음 할 일을, 교직원은 담당 범위의 모든 유형 요청과 답변 주체를 봐요(FR-02). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 아래 쿼리 필드. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 학부모는 같은 기관의 본인 요청을 봐요. 담임은 오늘 유효한 classroom_staff의 반 요청과 재배정받은 카드의 요청(상세 5번과 같은 예외), 원장은 같은 기관 전체를 봐요. 범위 밖 classroom_id는 404예요. |
| ⑥ 정상 응답 | 200 + `items[]`·`total`·`page`·`size`. 해당 요청이 없으면 빈 목록. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 조회할 때 보류 만료와 상담 시간 만료를 반영하고, 정렬한 뒤 쪽을 나눈다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `status` | 쿼리 | string | 선택 | 생략 가능 | 3.2의 요청 상태 11개 | 생략하면 모든 상태 |
| `page`·`size` | 쿼리 | integer | 선택 | 불가 | 기본 1·20, page ≥ 1, size 1~100 | 쪽 나누기 |
| `sort` | 쿼리 | string | 선택 | 불가 | `-created_at`(기본)·`created_at`·`-updated_at`·`updated_at` | 생성·변경 시각 순 |
| `answered_by`·`classroom_id`·`type` | 쿼리 | string·UUID·string | 선택 | 생략 가능 | agent·staff / 담당 범위 반 / 등록 유형 5개 | 교직원 필터예요. 학부모는 유효한 값을 보내도 무시하고, 잘못된 타입·허용 값은 422로 막아요. |
| `items[].id`·`type`·`title`·`status`·`status_label`·`updated_at` | 응답 | UUID·string·datetime | 항상 | title은 null 가능 | 등록 유형 5개·상태 11개 | 본인 요청의 요약 |
| `items[].next_action` | 응답 | string | 항상 | null 가능 | 정보 보완·시간 선택·민원 회신 확인 | needs_info면 보완 또는 시간 선택, 확인하지 않은 민원 회신이 있으면 확인 안내 |
| `items[].hold_until` | 응답 | date | 항상 | null 가능 | 보류 카드의 예정일 | 할 일이나 보류가 없으면 해당 칸은 null |
| `total`·`page`·`size` | 응답 | integer | 항상 | 불가 | 전체 건수·요청한 쪽·크기 | 목록 공통 칸 |

학부모는 기존 `RequestList` 모양을 그대로 받아요. 교직원은 `StaffRequestList`로 같은 요약 칸에 `classroom_id`·`child_id`·`child_name`·`requester_name`·`answered_by`를 더 받아요. 반·아이가 없는 요청도 원장은 볼 수 있고 classroom_id·아이 두 칸은 null이 될 수 있어요. 이름은 현재 표시 이름이에요. 교직원 `status_label`은 `staff_label`을 써요. `next_action`은 투약·귀가의 received면 confirm, assigned면 complete, 나머지는 null이에요. `hold_until`은 기존 보류 예정일이에요.

`answered_by=agent`는 `out_of_scope_answered` 이력이 있는 요청이에요. 서비스가 할 수 없는 질문에 정해진 문구로 바로 안내한 건이고 AI가 쓴 답은 아니에요(화면에는 '바로 안내'처럼 보여 줘요). 그 밖에 현재 상태나 이력이 `sent_or_booked`·`completed`까지 간 요청은 staff, 아직 답하지 않았으면 null이에요. 답변 뒤 대화가 이어져도 이력을 유지해요. AI 바로 안내는 카드 없이도 이 목록에서 찾아요.

```http
GET /api/v1/requests?status=needs_info
HTTP/1.1 200 OK
{"total": 1, "page": 1, "size": 20, "items": [{"id": "00000000-0000-4000-8000-000000000701", "type": "consultation", "title": "아이 친구 관계 상담", "status": "needs_info", "status_label": "시간을 골라 주세요", "updated_at": "2026-11-18T10:00:00+09:00", "next_action": "시간을 골라 주세요", "hold_until": null}]}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 교직원이 담당 범위 밖 classroom_id를 보냄 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.10 대화 이어 쓰기 — `POST /api/v1/requests/{request_id}/messages`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 학부모가 진행 중인 요청에 설명을 더한다(FR-02). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | `request_id`(UUID, 필수). |
| ④ 요청 본문 | `body`(아래 표). |
| ⑤ 검증·권한 | 본인 요청에만 쓸 수 있고, `completed`·`rejected`인 요청은 409로 막는다. |
| ⑥ 정상 응답 | 201 + `message`. 다음 상태는 요청 상세(3.2)에서 확인한다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 추가 글은 `message_added` 이력으로 남긴다. 문의·민원 회신 뒤(`sent_or_booked`)의 추가 글은 아래 규칙으로 회신 카드를 다시 열고 `awaiting_review`로 돌린다. 다른 상태에서는 AI를 다시 실행하지 않고 상태별 담당자 알림을 만든다. 투약·귀가는 기존처럼 입력 판을 올리고 확인을 풀어 `received`로 돌리며 `care_requested` 알림을 보낸다. |

| 글을 더한 당시 상태 | 문의·민원·상담의 처리 |
| --- | --- |
| `received`·`classified`·`assigned` | 추가 알림 없음. AI가 만든 카드 상세의 `messages[]`에서 대화를 읽는다. |
| `awaiting_review`·`on_hold`·`escalated`·상담 아닌 `needs_info` | 같은 요청의 열린 카드(`done`·`rejected` 제외) 담당자마다 `parent_message` 알림을 하나씩 보낸다. 담당자가 없으면 원장에게 보낸다. 상태는 그대로다. |
| 상담 `needs_info`·`sent_or_booked` | 담임(없으면 원장)에게 `parent_message`만 보낸다. 상담 후보·예약과 카드 상태는 그대로다. |
| 문의·민원 `sent_or_booked` | 최신 `reply_draft`를 다시 열어 판을 1 올리고 닫힌 시각·보류 예정일을 지운다. `draft.text`는 빈 문자열, `check_result`는 null, 직전 발송 글은 `draft.previous_text`로 남긴다. 카드가 없으면 현재 유효한 담임에게 초안 없는 회신 카드를 새로 만들고, 담임이 없으면 `unassigned`다. 학부모 확인을 지우고 요청을 `awaiting_review`로 돌려 `new_card` 알림을 보낸다(담당 없으면 원장). |

`parent_message` 제목은 “학부모가 글을 더 남겼어요”다. 다시 연 카드의 빈 초안을 그대로 `approve`하면 기존 규칙대로 409 `INVALID_TRANSITION`이다. 담임은 `edit_approve`에 직접 쓴 `edited_content.text`를 넣어야 보낼 수 있다. 이전 발송 글은 요청 대화에도 그대로 남는다.

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `request_id` | 경로 | string(UUID) | 필수 | 불가 | 본인 요청 | 대화를 이을 요청 |
| `body` | 본문 | string | 필수 | 불가 | 1~2,000자 | 추가 설명; 모의 구현은 공백만 있는 글도 길이로만 검사 |
| `message.id` | 응답 | integer | 항상 | 불가 | 서버 발급 | 메시지 ID |
| `message.sender_type`·`body`·`created_at` | 응답 | string·datetime | 항상 | 불가 | sender_type은 `user` | 저장한 글과 시각 |
| `message.sender_role` | 응답 | string | 항상 | 불가 | `parent` | 메시지를 쓴 사람의 역할. 이 API는 학부모만 부르므로 항상 `parent`다 |

```http
POST /api/v1/requests/00000000-0000-4000-8000-000000000702/messages
{"body": "버스 도착 시각을 더 알려드릴게요."}
HTTP/1.1 201 Created
{"message": {"id": 1071, "sender_type": "user", "sender_role": "parent", "body": "버스 도착 시각을 더 알려드릴게요.", "created_at": "2026-11-18T10:00:00+09:00"}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `INVALID_TRANSITION` | 끝난 요청에 글을 더함 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.11 알림 목록·읽음 — `GET /api/v1/notifications`, `POST /api/v1/notifications/{notification_id}/read`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 내 알림을 보고, 읽은 시각을 남긴다(FR-12). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 목록은 page·size·sort, 읽음은 정수 notification_id. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 로그인한 모든 역할이 쓴다. 같은 기관의 본인 알림 가운데 deliver_after가 지난 것만 보이고, 읽음도 이 범위 안에서 찾는다. |
| ⑥ 정상 응답 | 목록 200 + 쪽 나눈 items[], 읽음 200 + notification. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 모의 발송기는 조회할 때 pending 알림을 sent로 바꾼다. 읽음을 여러 번 보내도 read_at은 처음 값을 유지한다. 예약된 알림은 정한 시각이 오기 전까지 목록과 읽음 양쪽에서 뺀다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `page`·`size` | 쿼리 | integer | 선택 | 불가 | 기본 1·20, page ≥ 1, size 1~100 | 쪽 나누기 |
| `sort` | 쿼리 | string | 선택 | 불가 | `-created_at`(기본)·`created_at` | 내림차순·오름차순 |
| `notification_id` | 읽음 경로 | integer | 필수 | 불가 | 목록에서 받은 ID | 0 이하도 형식상 정수로 보고, 해당 알림이 없으면 404 |
| `items[].id`·`kind`·`title` | 목록 응답 | integer·string | 항상 | 불가 | kind에 parent_message(“학부모가 글을 더 남겼어요”)를 포함하며, 상담 알림 consultation_ending·consultation_delayed, 투약·귀가 알림 care_requested·care_confirmed·care_rejected·cancelled도 포함하며, note_corrected("알림장이 고쳐졌어요", 3.30) 정정 알림도 준다. 문의·상담 위험에도 urgent_complaint·uncertain_complaint라는 이름을 그대로 쓴다. 제목만 '긴급 문의'·'AI 판단 불확실 상담'처럼 요청 유형에 맞춘다 | 알림 종류와 제목 |
| `items[].body`·`request_id`·`subject_type`·`subject_id` | 목록 응답 | string·UUID | 항상 | null 가능 | 알림장 알림은 subject_type=`daily_note` | 내용과 연결 대상 |
| `items[].read_at`·`deliver_after` | 목록 응답 | datetime | 항상 | read_at만 null 가능 | 한국 시간 포함 | 읽은 시각과 노출 시각; 읽음 응답의 notification도 같은 모양 |
| `total`·`page`·`size` | 응답 | integer | 항상 | 불가 | 전체 건수·요청한 쪽·크기 | 목록 공통 칸 |

상담 확정은 `consultation_booked`("상담 예약 확정", 본문은 한국 날짜·시간), 재배정은 새 담당에게 `reassigned`("요청이 배정됐어요")로 알린다. 반려(`dismiss`)의 `rejected` 알림 본문은 6장 사유 코드의 표시 이름과 선택한 `reason_text`를 ` · `로 잇는다. 예를 들어 `policy`만 있으면 "원 방침과 다름", `other`와 이유 글이 있으면 "기타 · 이유 글"이다. 원문 사유 코드는 본문에 쓰지 않는다.

```http
GET /api/v1/notifications?size=1
HTTP/1.1 200 OK
{"total": 2, "page": 1, "size": 1, "items": [{"id": 1013, "kind": "needs_info", "title": "정보가 더 필요해요", "body": "시간을 골라 주세요", "request_id": "00000000-0000-4000-8000-000000000701", "subject_type": null, "subject_id": null, "read_at": null, "deliver_after": "2026-11-18T10:00:00+09:00"}]}
POST /api/v1/notifications/1013/read
HTTP/1.1 200 OK
{"notification": {"id": 1013, "kind": "needs_info", "read_at": "2026-11-18T10:00:00+09:00", "deliver_after": "2026-11-18T10:00:00+09:00"}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |


### 3.12 받은함 — `GET /api/v1/cards`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임·원장이 받은함 카드와 필터별 건수를 본다(FR-09). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 파라미터와 화면용으로 더한 칸은 3.7 참고. sort는 받지 않는다. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 담임은 현재 담당 반 카드나 본인에게 배정된 카드를, 원장은 같은 기관 전체를 본다. |
| ⑥ 정상 응답 | 200 + items[]·counts·type_counts·total·page·size. filter를 생략하면 done을 뺀다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 만료를 반영한 뒤 긴급 우선 → due_at이 있는 카드 우선 → due_at 오름차순 → 카드 UUID 문자열 순으로 정렬한다. 완료된 카드라도 기한이 지났으면 is_delayed 값 자체는 참일 수 있다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `filter`·`request_type`·`risk_level`·`kind`·`assignee`·`page`·`size` | 쿼리 | 3.7 참고 | 선택 | 생략 가능 | 3.7 참고 | 기본 size=20, 최대 100 |
| `items[].id`·`kind`·`status`·`version`·`title` | 응답 | UUID·string·integer | 항상 | 불가 | 카드 종류 6개, version ≥ 1 | status는 카드 내부 값 |
| `items[].status_label`·`request_type`·`urgency`·`is_urgent` | 응답 | string·boolean | 항상 | request_type·urgency는 null 가능 | is_urgent는 요청의 risk_level이 urgent인지 여부 | 표시 이름은 요청 상태 기준 |
| `items[].assignee`·`due_at`·`is_delayed`·`hold_until` | 응답 | object·datetime·boolean·date | 항상 | is_delayed 외 null 가능 | assignee={id, display_name}; due_at < 현재면 지연 | 화면용 더한 칸은 3.7 참고 |
| `counts` | 응답 | object(integer) | 항상 | 불가 | 필터 6개를 모두 넣고 없으면 0 | 역할·risk_level·kind·assignee·request_type 조건 안에서, filter를 적용하기 전에 카드 수를 셈 |
| `type_counts` | 응답 | object(integer) | 항상 | 불가 | all·complaint·consultation·inquiry | 역할·risk_level·kind·assignee·filter 조건 안에서, request_type을 적용하기 전에 셈 |
| `total`·`page`·`size` | 응답 | integer | 항상 | 불가 | 전체 건수·요청한 쪽·크기 | 목록 공통 칸 |

카드마다 아래 순서로 따져서 처음 맞는 필터 하나에만 넣는다. ① 끝난 카드·요청은 `done`(단, 회신한 민원의 reply_draft 중 거절되지 않은 것은 처리 완료 전까지 예외) ② 카드나 요청이 보류 중이면 `on_hold` ③ 담당이 없으면 `unassigned` ④ 요청이 `escalated`인 `reply_draft`는 위험 등급에 관계없이 `in_progress` ⑤ 위험 등급이 uncertain이면 `uncertain` ⑥ awaiting_review·escalated, 학부모가 확인한 회신 민원, 요청 없는 카드는 `needs_review` ⑦ 나머지는 `in_progress`. 원장 대기 중인 회신 카드는 목록과 상세의 `request.status_label`에 "원장 확인 중"을 표시하며, 원장 보고 카드는 기존 표시·필터를 유지한다. 원장 지시나 원장의 일반 재분류로 `awaiting_review`가 되면 회신 카드는 기존 위험 등급에 맞는 필터로 돌아간다. DB 뷰는 0013 마이그레이션으로 바꾼다.
종류 건수도 요청 수가 아니라 카드 수다. `type_counts.all`은 요청 없는 카드까지 세므로 세 유형 건수를 더한 값보다 클 수 있다. 완료 카드는 counts에는 들어가지만, type_counts에서는 filter가 없을 때 빠진다.

```http
GET /api/v1/cards?filter=needs_review&request_type=complaint&page=3&size=1
HTTP/1.1 200 OK
{"items": [{"id": "00000000-0000-4000-8000-000000000802", "kind": "reply_draft", "version": 1, "request_type": "complaint", "is_urgent": false}], "counts": {"unassigned": 0, "needs_review": 3, "uncertain": 2, "on_hold": 1, "in_progress": 0, "done": 0}, "type_counts": {"complaint": 3, "consultation": 0, "inquiry": 0, "all": 4}, "total": 3, "page": 3, "size": 1}
```


| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.13 카드 상세·교직원 스트림 — `GET /api/v1/cards/{card_id}`, `GET …/stream`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 교직원이 초안·근거·위험·전체 이력을 보고, 스트림으로 단계·초안 글자·카드를 받는다(FR-04·07·09·11, NFR-10). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). 스트림은 `Accept: text/event-stream`을 보내고 fetch 스트림으로 읽는다. |
| ③ 경로·쿼리 | card_id(UUID, 필수). |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 담임은 담당 반 카드나 본인에게 배정된 카드를, 원장은 같은 기관 전체를 본다. 학부모는 403, 범위 밖은 404. |
| ⑥ 정상 응답 | 상세는 200 + 아래 칸. 스트림은 200 text/event-stream, Cache-Control: no-cache. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 조회할 때 해당 요청의 만료를 반영한다. 모의 스트림은 classifying→searching→drafting→checking 단계, text를 12자씩 나눈 token, card, done 순으로 재생한다. text가 없으면 token을 보내지 않고, 요청 없는 카드면 done.request_status가 null이다. 이벤트 간격은 기본 300ms이고, 연결할 때마다 다시 재생한다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `card_id` | 경로 | string(UUID) | 필수 | 불가 | 권한 범위 안 | 상세·스트림 공통 |
| `card.id`·`kind`·`status`·`version`·`summary`·`draft`·`check_result`·`check_attempts` | 응답 | UUID·string·integer·object | 항상 | check_result만 null 가능 | draft는 객체, check_attempts는 검사 횟수 | summary 등 화면용 칸은 3.7 참고 |
| `request` | 응답 | object | 항상 | null 가능 | 3.2 요약 + body·risk_level·risk_category·repeat_count·classroom_id | 요청 없는 카드면 null |
| `messages[]` | 응답 | object[] | 항상 | 빈 목록 가능 | id·sender_type·sender_role·body·created_at(3.2와 같음) | 요청의 전체 대화. 요청 없는 카드면 빈 목록 |
| `evidence[]`·`warnings[]`·`parent_choices[]`·`rule`·`director_instruction` | 응답 | 목록·object | 항상 | rule·director_instruction은 null 가능 | 3.7 참고 | 근거·경고·선택 시간·규칙·원장 지시 |
| `timeline[]` | 응답 | object[] | 항상 | 빈 목록 가능 | id·action·request_id·card_id·agent_name·actor_type·actor_id·from_status·to_status·detail·created_at | 같은 요청의 이력 또는 해당 카드의 이력을 저장 순서대로 |
| `stage`·`token`·`card`·`done` | SSE data | object | 이벤트별 | request_status는 null 가능 | {stage, at}·{text}·{id, status, version}·{request_status} | token·card는 교직원만 받음 |

```http
GET /api/v1/cards/00000000-0000-4000-8000-000000000802
HTTP/1.1 200 OK
{"card": {"id": "00000000-0000-4000-8000-000000000802", "kind": "reply_draft", "status": "pending", "version": 1, "summary": "등원 버스가 늦었어요", "draft": {"summary": "등원 버스가 늦었어요", "text": "(모의 초안) 말씀해 주셔서 감사합니다. 확인해서 다시 안내드릴게요.", "no_evidence": false}}, "messages": [{"id": 1001, "sender_type": "user", "sender_role": "parent", "body": "등원 버스가 늦었어요", "created_at": "2026-11-18T09:00:00+09:00"}], "warnings": [], "parent_choices": [], "rule": null, "director_instruction": null}
GET /api/v1/cards/00000000-0000-4000-8000-000000000802/stream
HTTP/1.1 200 OK
Content-Type: text/event-stream
event: token
data: {"text": "(모의 초안) 말씀해 "}

event: card
data: {"id": "00000000-0000-4000-8000-000000000802", "status": "pending", "version": 1}

event: done
data: {"request_status": "awaiting_review"}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.14 위험 등급 다시 분류 — `POST /api/v1/cards/{card_id}/reclassify`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 교직원이 문의·민원의 위험 등급을 일반 또는 긴급으로 다시 정한다(FR-03·07). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | card_id(UUID, 필수). |
| ④ 요청 본문 | 아래 필드 표. |
| ⑤ 검증·권한 | 담임·원장만 호출할 수 있고, 원장 보고 카드는 원장만 다룬다. 요청은 문의·민원이면서 awaiting_review·escalated 상태여야 하고, 판도 확인한다. 다만 대상을 uncertain으로만 좁히지는 않는다. 상담은 담임이 시간을 확정하는 흐름이라 재분류하지 않는다. 상담을 재분류하려는 요청에는 409를 돌려준다. |
| ⑥ 정상 응답 | 200 + 교직원용 request. 응답에 card가 없으니 새 판은 카드 상세에서 받는다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 일반으로 바꾸면 risk_category를 지운다. 열린 원장 보고 카드가 있을 때 담임이 호출하면 위험 등급만 바꾸고 escalated는 그대로 둔다. 원장이 일반으로 내리면 열린 원장 보고 카드를 done으로 닫고, risk_reclassified 이력에 그 카드 ID를 남긴 뒤 요청을 awaiting_review로 바꾼다. 이렇게 escalated에서 담임 회신 단계로 돌아오는 경우에는 회신 카드 담당자에게 그 회신 카드로 이어지는 new_card 알림을 한 번 남긴다. 열린 보고 카드가 없으면 일반은 awaiting_review로 바꾸고, 긴급은 원장 보고 카드를 확보한 뒤 escalated로 바꾼다. 공통으로 같은 요청 카드의 due_at을 접수 시각 기준으로 다시 계산하고, 호출한 카드와 이번에 닫은 보고 카드의 판을 각각 1 올린다. 일반·판단 필요에서 긴급으로 올리면 열린 reply_draft의 text를 비우고 check_result를 null로 지우며 그 회신 카드의 판도 1 올린다(호출 대상이면 한 번만). 완료·반려한 옛 회신은 보존한다. 초안은 새로 만들지 않으며, 그 밖의 재분류에서는 new_card 알림을 만들지 않는다. 사람이 올린 escalated 이력의 detail.reason은 manual이고, risk_reclassified.detail.reason에는 사람이 적은 이유를 그대로 남긴다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `card_id` | 경로 | string(UUID) | 필수 | 불가 | 권한 범위 안 | 위험 등급을 바꿀 카드 |
| `version` | 본문 | integer | 필수 | 불가 | 1 이상 | 화면이 본 카드 판 |
| `risk_level` | 본문 | string | 필수 | 불가 | `normal`·`urgent` | 새 등급 |
| `risk_category` | 본문 | string | 긴급이면 필수 | 일반은 null 가능 | `child_safety`·`staff_attack`·`legal_external`·`privacy_leak` | 일반이면 보내도 저장하지 않음 |
| `reason` | 본문 | string | 필수 | 불가 | 1~500자, 공백만 불가 | 처리 이유 |
| `request` | 응답 | object | 항상 | 불가 | 3.13 교직원 요청과 같은 모양 | risk_level·risk_category·status 등을 돌려줌 |

```http
POST /api/v1/cards/00000000-0000-4000-8000-000000000802/reclassify
{"version": 1, "risk_level": "normal", "reason": "일반 민원으로 확인함"}
HTTP/1.1 200 OK
{"request": {"id": "00000000-0000-4000-8000-000000000702", "risk_level": "normal", "risk_category": null, "status": "awaiting_review", "status_label": "확인 필요"}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `CARD_VERSION_CONFLICT`·`INVALID_TRANSITION` | 판 불일치(details.current_version)·민원 아님·상태가 맞지 않음 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.15 원장 보고 지시 — `POST /api/v1/cards/{card_id}/instructions`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 원장이 보고 카드에 지시를 남기고 담임에게 처리를 넘긴다(FR-07). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | card_id(UUID, 원장 보고 카드). |
| ④ 요청 본문 | version·instruction. |
| ⑤ 검증·권한 | 역할은 director만. 카드는 같은 기관의 director_report이면서 pending·in_review 상태여야 하고, 요청은 escalated여야 한다. 판과 함께, 같은 판에 이미 내린 결정이 있는지도 확인한다. |
| ⑥ 정상 응답 | 200 + done 카드(판 +1)·awaiting_review 요청·next_card_id=null. 회신 담당이 없으면 next_action="reassign"과 재배정 안내 message, 담당이 있으면 두 칸은 null. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 결정은 instruct로, 지시 내용은 reason_text로 기록한다. 기존 회신 카드 상세의 director_instruction에는 최신 지시가 붙는다. pending·in_review뿐 아니라 unassigned 회신 카드에도 지시를 붙인다. 회신 카드는 미배정 상태·담당 없음 그대로 두고, 응답의 next_action="reassign"과 message="지시를 남겼어요. 회신 카드를 담당 선생님에게 재배정해 주세요."로 다음 행동을 안내한다. 회신 카드의 판과 초안은 바꾸지 않고, 승인·발송은 따로 한다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `card_id` | 경로 | string(UUID) | 필수 | 불가 | 원장 보고 카드 | 3.3 원장 보고 결과나 받은함에서 받은 ID |
| `version` | 본문 | integer | 필수 | 불가 | 1 이상 | 화면이 본 카드 판 |
| `instruction` | 본문 | string | 필수 | 불가 | 1~500자, 공백만 불가 | 원장 지시 |
| `card.id`·`status`·`version` | 응답 | UUID·string·integer | 항상 | 불가 | status=`done` | 끝난 보고 카드와 새 판 |
| `request`·`next_card_id` | 응답 | object·UUID | 항상 | next_card_id는 null | request={id, status, parent_confirmed_at} | 요청 상태는 awaiting_review |
| `next_action`·`message` | 응답 | string | 항상 | 담당 있으면 null | next_action은 reassign 또는 null | 미배정 회신은 재배정 안내 문구를 함께 돌려줌 |

```http
POST /api/v1/cards/{card_id}/instructions
{"version": 1, "instruction": "운행 시각을 확인하고 보호자에게 안내해 주세요."}
HTTP/1.1 200 OK
{"card": {"id": "…", "status": "done", "version": 2}, "request": {"id": "00000000-0000-4000-8000-000000000702", "status": "awaiting_review", "parent_confirmed_at": null}, "next_card_id": null, "next_action": null, "message": null}
```


| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `ALREADY_DECIDED`·`CARD_VERSION_CONFLICT`·`INVALID_TRANSITION` | 같은 판의 기존 결정·판 불일치·카드 종류나 상태 불일치 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.16 담당 재배정 — `POST /api/v1/cards/{card_id}/reassign`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 원장이 카드 담당자를 바꾸고 이유를 남긴다(FR-09·19). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | card_id(UUID, 필수). |
| ④ 요청 본문 | assignee_id·reason. version은 받지 않는다. |
| ⑤ 검증·권한 | director만. 배정 대상은 같은 기관의 활성 teacher여야 한다(고를 목록은 API 70, 3.38). director_report 카드나 done·rejected 카드는 재배정하지 못한다. |
| ⑥ 정상 응답 | 200 + card { assignee { id, display_name }, version }. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 카드의 담당과 연결된 요청의 담당을 함께 바꾸고 카드 판을 1 올린다. unassigned 카드는 pending으로 바꾼다. 새 담당에게 reassigned("요청이 배정됐어요") 알림을 남긴다. 예약 확정 전 상담의 proposed·chosen_by_parent 후보는 새 담당의 바쁜 시간·확정 예약(지연 종료 시각 포함)과 다시 비교해 겹치는 것만 discarded로 버리고, 남은 후보의 teacher_id를 바꾼 뒤 버린 수만큼 다음 회차에서 가능한 후보를 채운다. 겹치지 않는 시각·체크는 보존하되, 학부모 체크를 버렸으면 남은 체크도 풀고 요청을 needs_info로 돌려 기존 needs_info 알림으로 다시 선택을 안내한다. 열린 후보가 없던 상담은 최대 세 개를 새로 계산하고 같은 안내를 남긴다. 그 밖의 요청 상태와 기한도 그대로 둔다. 다른 반 교사에게도 배정할 수 있고, 이력에는 from·to·reason을 남긴다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `card_id` | 경로 | string(UUID) | 필수 | 불가 | 처리 가능한 카드 | 배정할 카드 |
| `assignee_id` | 본문 | string(UUID) | 필수 | 불가 | 같은 기관의 활성 teacher | 새 담당자 |
| `reason` | 본문 | string | 필수 | 불가 | 1~500자, 공백만 불가 | 처리 이유 |
| `card.assignee` | 응답 | object | 항상 | 불가 | id(UUID)·display_name(string) | 새 담당자 |
| `card.version` | 응답 | integer | 항상 | 불가 | 이전 판 +1 | 다음 결정에 쓸 판 |

```http
POST /api/v1/cards/00000000-0000-4000-8000-000000000802/reassign
{"assignee_id": "00000000-0000-4000-8000-000000000202", "reason": "담당자 부재로 재배정함"}
HTTP/1.1 200 OK
{"card": {"assignee": {"id": "00000000-0000-4000-8000-000000000202", "display_name": "햇님반 선생님"}, "version": 3}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 카드 범위 밖·대상 없음·다른 기관·비활성·교사 아님 |
| 409 | `INVALID_TRANSITION` | 원장 보고·개인 규칙 제안·끝난 카드 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.17 개인 규칙 제안 켜기·거절 — `POST /api/v1/memory-rules/{rule_id}/decision`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 규칙 주인이 제안을 켜거나 거절한다(FR-06). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | rule_id(UUID, 필수). |
| ④ 요청 본문 | decision. |
| ⑤ 검증·권한 | 로그인한 규칙 주인만. 같은 기관인지, 규칙 주인인지는 검사하지만 역할이 다르다는 이유만으로 403을 내지는 않는다. activate·decline은 proposed 규칙만, off는 active 규칙만 받는다. 그 밖은 409 INVALID_TRANSITION. |
| ⑥ 정상 응답 | 200 + rule { id, status }. activate는 active, decline은 declined, off는 off. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 연결된 제안 카드를 done으로 바꾸고 판을 1 올린다. 켜면 approve, 거절하면 reject로 결정과 이력을 남긴다. 같은 규칙을 다시 요청하면 409다. 모의 상담 후보에는 규칙을 적용하지 않는다. |

DB 모드도 같은 결정 계약을 쓴다. 카드를 거절하거나 반려한 이유는 결정한 담임의 기억에 저장하는데, 이때 출처 요청이 속한 반의 아이 이름을 가린다. 반이 없으면 같은 기관 전체의 아이 이름을 본다. 이름은 앞에 한글이 없고 뒤에 글 끝·공백·문장부호나 조사·호칭이 올 때만 가리며, 다른 낱말 안에 섞인 글자는 그대로 둔다. 지우지 않은 기억 가운데 같은 코드가 세 건 이상이면 제안 카드 하나를 만든다. 같은 주인·같은 코드에 decline 결정이 있었다면, 마지막 decline 뒤로 새 기억이 세 건 쌓여야 다시 제안한다. 개인 규칙 제안은 재배정하지 않고, 주인에게 근무 시간을 기준으로 new_card 알림을 남긴다. 자동 대역은 코드별 안내만 제안하며, `other` 자유 글로는 자동 규칙을 만들지 않는다. 구체적인 조건은 기억 AI가 뽑아내고, DB의 상담 계산은 `active` 상태인 `slot_unavailable` 규칙의 시간 조건만 읽는다.

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `rule_id` | 경로 | string(UUID) | 필수 | 불가 | 본인 규칙 | 카드 상세 rule.id |
| `decision` | 본문 | string | 필수 | 불가 | `activate`·`decline`·`off` | 켜기·거절·켜 둔 규칙 끄기(FR-20) |
| `rule.id` | 응답 | string(UUID) | 항상 | 불가 | 요청한 규칙 ID | 결정 대상 |
| `rule.status` | 응답 | string | 항상 | 불가 | `active`·`declined` | 저장한 상태 |

```http
POST /api/v1/memory-rules/00000000-0000-4000-8000-000000000d01/decision
{"decision": "activate"}
HTTP/1.1 200 OK
{"rule": {"id": "00000000-0000-4000-8000-000000000d01", "status": "active"}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `INVALID_TRANSITION` | proposed가 아닌 규칙, 같은 결정의 반복 포함 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

### 3.18 원장 현황 — `GET /api/v1/overview`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 원장이 기관 전체의 대기·지연·처리 결과와 재배정 이력을 본다(FR-09·19). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 없음. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | director만. 모든 집계는 같은 기관 안에서 한다. |
| ⑥ 정상 응답 | 200 + 아래 숫자 5개·reassignments[]·eval[]. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 집계하기 전에 만료를 먼저 반영한다. 숫자는 카드 단위로 세지만 completed_unconfirmed만은 다르다. 최근 30일 안에 닫힌 done 카드의 요청 ID를 중복 없이 모은 뒤, 그중 민원이면서 completed이고 학부모가 아직 확인하지 않은 요청을 센다. 모의 eval은 빈 목록이다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `unassigned` | 응답 | integer | 항상 | 불가 | 받은함 필터 unassigned인 카드 수 | 미배정 |
| `waiting`·`delayed` | 응답 | integer | 항상 | 불가 | pending·in_review·on_hold 수 / 그중 due_at이 지난 수 | 대기·지연 |
| `done_today` | 응답 | integer | 항상 | 불가 | status=done이고 closed_at의 한국 날짜가 오늘 | 오늘 닫은 카드 수; 요청 완료 수와 다름 |
| `completed_unconfirmed` | 응답 | integer | 항상 | 불가 | 위 실행 규칙; 최근 30일 | 학부모 미확인 완료 요청 수 |
| `reassignments[]` | 응답 | object[] | 항상 | 빈 목록 가능 | card_id·from(null 가능)·to·reason·at | 기관의 전체 재배정 이력, 저장 순서 |
| `eval[]` | 응답 | object[] | 항상 | 빈 목록 가능 | suite·requested_model·returned_model(null 가능)·passed·total·started_at | 평가 결과; 모의 값은 [] |

```http
GET /api/v1/overview
HTTP/1.1 200 OK
{"unassigned": 1, "waiting": 8, "delayed": 0, "done_today": 1, "completed_unconfirmed": 0, "reassignments": [], "eval": []}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |

### 3.19 알림장 초안 만들기·진행 상태 — `POST /api/v1/daily-notes/drafts`, `GET …/drafts/{input_id}`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임이 반 전체 알림장 초안을 만들고 작업 상태를 확인한다(FR-10). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`; 상태 조회는 본문 없음. |
| ③ 경로·쿼리 | 상태 조회에만 input_id(UUID, 필수). |
| ④ 요청 본문 | 생성할 때 classroom_id·note_date·activities·supplies를 보내고, child_memos[]는 선택으로 보낸다. |
| ⑤ 검증·권한 | teacher만, 현재 담당 반에 대해서만 호출할 수 있다. note_date는 오늘이나 지난날이어야 한다. 같은 반·날짜의 작업이 이미 있으면 입력 내용이 달라도 기존 작업을 돌려준다. |
| ⑥ 정상 응답 | 생성은 202, 중복은 200, 상태 조회는 200이고, 셋 다 input_id·draft_status·error를 담는다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 202를 받은 뒤 작업 상태는 GET /daily-notes/drafts/{input_id}로, 아이별 결과는 GET /daily-notes?classroom_id=&date=(3.20)로 확인한다. 모의 생성은 바로 succeeded가 되지만, activities에 [실패]가 들어 있으면 failed가 된다. 실패한 경우에도 작업과 확인 카드는 남는다. 첫 생성 실패에는 아이별 알림장이 없고, 다시 만들기 실패에는 기존 알림장을 보존한다. 워커 큐 등록(`publish`)이 실패해도 입력을 `queued`에 남기지 않고 `failed`로 바꾸며 반 카드에 `tool_failed` 이력과 `detail.detected_failure = "queue_error"`를 남긴다. 담임이 다시 만들기로 재접수한다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `input_id` | 조회 경로·응답 | string(UUID) | 조회·응답 필수 | 불가 | 접수 응답에서 받은 값 | 상태 조회 키 |
| `classroom_id` | 생성 본문 | string(UUID) | 필수 | 불가 | 현재 담당 반 | 초안을 만들 반 |
| `note_date` | 생성 본문 | date | 필수 | 불가 | YYYY-MM-DD, 오늘 또는 지난날 | 알림 날짜 |
| `activities` | 생성 본문 | string | 필수 | 불가 | 1~2,000자 | 오늘 활동 |
| `supplies` | 생성 본문 | string | 필수 | 빈 문자열 가능 | 최대 2,000자 | 준비물이 없어도 칸은 보냄 |
| `child_memos[]` | 생성 본문 | object[] | 선택 | 빈 목록 가능 | 생략하면 [] | 아이별 메모 |
| `child_memos[].child_id` | 생성 본문 | string(UUID) | 항목마다 필수 | 불가 | 그 반 아이, 중복 불가 | 다른 반·다른 기관 아이거나 없는 아이면 422이고, details.child_id에 그 ID가 온다 |
| `child_memos[].memo` | 생성 본문 | string | 항목마다 필수 | 빈 문자열 불가 | 1~500자 | 모의 생성은 원문을 그대로 child 줄에 넣고, 공백뿐이면 줄을 만들지 않는다 |
| `draft_status`·`error` | 응답 | string·object | 항상 | error는 null 가능 | queued·running·succeeded·failed; 오류는 {code, message} | 실패 조회도 200, 모의 오류 코드는 UPSTREAM_UNAVAILABLE |

초안을 만드는 입구 함수의 전체 입력은 `{ input_id, note_date, classroom, activities, supplies, children, roster_names, menu }`이고, 이 중 `menu`는 `{ document_id, title, text }` 또는 null이다. `roster_names`는 반 전체 아이 이름이며, 부분 재생성으로 `children`을 걸러도 유지한다(3.26). 아이별 입력은 `{ child_id, display_name, memo, requests: [{ request_id, type, text }] }`다. `requests`는 클라이언트가 보내지 않고 서버가 모은다. 같은 기관·반·아이의 보호자가 보낸 `medication`·`pickup` 요청 가운데 `created_at`의 한국 날짜가 `note_date`인 것을 모으며, 해당 요청이 없으면 빈 목록이다. 문의·상담·민원은 답이 있어야 끝나는 일이라 알림장에 넣지 않고 받은함에서만 다룬다(알림장은 아이의 하루·식사·투약·귀가·준비물, 기획서 FR-14). 각 항목의 `text`에는 보호자 요청 본문이 들어간다. DB 모드의 실행기(runner)도 이 입구를 같은 모양으로 부른다.

모의 초안은 요청 원문을 `source: { type: request, request_id }` 줄에 넣는다. 하늘의 "기침해요"와 다른 귀가 요청은 반영하지만, 노을의 고정 귀가 요청(…70a) 하나만은 일부러 빼서 `request_missed`를 보여 준다. 이 항목은 `item_key: pickup`, `sentence: null`, `request_id: …70a`다. 교사는 요청을 확인한 뒤 기존 PATCH의 `resolved_checks`로 해결한다. 미해결 항목이 남아 있으면 확인·발송을 막는 규칙도 기존과 같다.

```http
POST /api/v1/daily-notes/drafts
{"classroom_id": "00000000-0000-4000-8000-000000000101", "note_date": "2026-11-18", "activities": "블록 놀이와 산책을 했어요.", "supplies": "내일 실내화", "child_memos": [{"child_id": "00000000-0000-4000-8000-000000000501", "memo": "블록으로 높은 탑을 쌓음"}]}
HTTP/1.1 202 Accepted
{"input_id": "…", "draft_status": "succeeded", "error": null}
GET /api/v1/daily-notes/drafts/{input_id}
HTTP/1.1 200 OK
{"input_id": "…", "draft_status": "succeeded", "error": null}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·길이, 중복 child_id, 그 반 아이가 아닌 메모(details.child_id) |

#### 3.19.1 접수부터 결과 조회까지 한 번에 따라가기

아래 응답은 2026-11-23 develop 코드에서 받은 JSON을 간추린 것이다. 모드를 따로 적지 않은 예시는 모의 모드에서 받았고, 새로 만든 ID는 `…`로 줄였다. 화면 연결은 첫 시연 때 점검한다.

**① 접수.** 담임이 반 입력을 보내면 202 응답과 입력 ID(`input_id`)를 받는다. 모의 모드에서는 접수와 동시에 초안을 다 만들기 때문에 상태가 처음부터 `succeeded`다. DB 모드에서는 `queued`로 응답한 뒤 백그라운드에서 처리하므로, 조회해 보면 상태가 `running`을 거쳐 `succeeded`로 바뀐다.

```http
POST /api/v1/daily-notes/drafts
{"classroom_id": "00000000-0000-4000-8000-000000000101", "note_date": "2026-11-23", "activities": "블록 놀이와 산책을 했어요.", "supplies": "내일 실내화", "child_memos": [{"child_id": "00000000-0000-4000-8000-000000000501", "memo": "블록으로 높은 탑을 쌓음"}]}
HTTP/1.1 202 Accepted
{"input_id": "…", "draft_status": "succeeded", "error": null}
```

같은 반·같은 날짜로 다시 보내면 내용이 달라도 새 작업을 만들지 않고, 200과 함께 처음 받은 `input_id`와 지금 상태를 돌려준다.

**② 진행 상태 조회.** 202는 접수했다는 뜻이고, 조회 응답의 200은 조회에 성공했다는 뜻이다. 초안이 잘 만들어졌는지는 상태 코드가 아니라 `GET /api/v1/daily-notes/drafts/{input_id}`가 돌려주는 `draft_status`로 판단한다. 가이드의 `job_id`는 우리 `input_id`이고, `status`는 `draft_status`다. 가이드는 결과를 `result`에 담지만, 우리는 아이별 알림장을 ③의 3.20으로 따로 받는다. 완료 시각 칸은 없다.

| 응답 | 뜻 | 화면이 할 일 |
| --- | --- | --- |
| 202 · `draft_status=queued`(모의는 바로 `succeeded`나 `failed`) | 처리 요청을 접수함 | 접수를 표시하고 진행 상태를 조회한다 |
| 200 · `queued`·`running` | 조회는 성공했고 아직 만드는 중 | 결과를 성공처럼 보여 주지 않고 다시 조회한다 |
| 200 · `succeeded` | 작업이 끝났고 아이별 초안이 저장됨 | ③에서 아이별 초안을 받아 보여 준다 |
| 200 · `failed` + `error` | 조회는 성공했지만 작업이 실패함 | `error.message`를 보여 주고 다시 만들기(3.26)를 안내한다 |
| 404 `NOT_FOUND` | 없는 입력 ID이거나 다른 반·다른 기관의 입력 | 자료가 있다는 사실도 알리지 않는다(1.2) |

다시 조회와 새로 실행은 다르다. 다시 조회는 같은 `GET …/drafts/{input_id}`를 부르는 것이라 아무것도 바꾸지 않는다. 새로 실행하는 것은 다시 만들기(3.26 `POST …/drafts/{input_id}/regenerate`)뿐이다. 같은 반·같은 날짜로 `POST /daily-notes/drafts`를 다시 보내도 새로 실행되지 않고, 이미 접수된 작업이 돌아온다. 그래서 접수 응답이 끊겼을 때 같은 값으로 다시 보내도 작업이 둘로 늘지 않는다. 진행 중 화면은 DB 모드에서 확인한다. 모의 모드는 접수하면서 결과를 다 만들기 때문에 진행 중 응답을 낼 수 없다.

**③ 아이별 초안 받기.** 작업이 완료되면 `GET /api/v1/daily-notes?classroom_id=…&date=…`(3.20)에서 아이마다 알림장을 하나씩 받는다. 확인할 항목이 있는 알림장은 `needs_check`이고, 없으면 `draft`다.

```http
GET /api/v1/daily-notes?classroom_id=00000000-0000-4000-8000-000000000101&date=2026-11-23&size=3&sort=created_at
HTTP/1.1 200 OK
{"total": 20, "page": 1, "size": 3, "items": [{"id": "…", "child_id": "00000000-0000-4000-8000-000000000501", "note_date": "2026-11-23", "status": "needs_check",
  "content": {"items": [{"key": "day", "label": "오늘 하루", "value": "블록 놀이와 산책을 했어요."}, …, {"key": "child", "label": "아이 메모", "value": "블록으로 높은 탑을 쌓음"}, …]},
  "open_checks": [{"id": "c1", "item_key": "supplies", "kind": "date_check", "problem": "준비물 날짜를 확인해 주세요", "sentence": "내일 실내화"}],
  "confirmed_at": null, "sent_at": null}, …]}
```

**작업 전체가 실패한 경우.** 큐 등록·작성기 입구 함수 실행·결과 저장에서 작업 전체가 실패하면 `draft_status=failed`로 끝난다. 첫 생성에서는 아이별 알림장이 없고, 다시 만들기에서는 기존 알림장을 보존한다. 이때 화면은 `error.message`와 다시 만들기 버튼을 보여 준다. 그래프 안의 아이별 모델 호출 실패는 아래의 `draft_failed` 확인 항목으로 남긴다. 모의 모드에서는 `activities`에 `[실패]`를 넣어 작업 전체 실패를 재현한다.

```http
GET /api/v1/daily-notes/drafts/{input_id}
HTTP/1.1 200 OK
{"input_id": "…", "draft_status": "failed", "error": {"code": "UPSTREAM_UNAVAILABLE", "message": "모델 응답이 없어 초안을 만들지 못했어요."}}
GET /api/v1/daily-notes?classroom_id=00000000-0000-4000-8000-000000000101&date=2026-11-22
HTTP/1.1 200 OK
{"total": 0, "page": 1, "size": 20, "items": []}
```

**모든 아이가 템플릿인 경우.** 아이별 알림장을 담임이 직접 고칠 수 있어 입력은 `succeeded`지만, `drafted.detail.validation_result=all_children_template`를 실패 incident로 집계한다. 반 카드 목록·상세의 `status_label`은 "AI가 못 만들었어요 · 직접 쓰거나 다시 만들기"이며, 아이별 `draft_failed`를 해결하기 전에는 발송할 수 없다.

**아이 한 명만 실패한 경우.** 작업은 `succeeded`로 끝나지만, 실패한 아이의 알림장에만 `draft_failed` 확인 항목이 남는다. 그 알림장에는 반 공통 줄만 있고 아이 메모 줄은 없다. 화면은 그 아이 알림장에 확인 항목을 띄우고, 담임은 알림장을 직접 써서 항목을 해결하거나 다시 만들기를 부른다. 모의 모드에는 이 경로가 없어서, 아래 응답은 DB 모드에서 아이 한 명의 초안 작성을 일부러 실패시켜 받았다. 응답에 나온 문장은 기본 작성기인 대역이 쓴 것이고, 그래프 작성기는 `problem`에 5.5.1의 문장을 쓴다.

```json
{"id": "…", "child_id": "00000000-0000-4000-8000-000000000501", "status": "needs_check",
 "open_checks": [{"id": "…", "item_key": "child", "kind": "draft_failed", "problem": "아이 메모 초안을 만들지 못했어요. 직접 확인해 주세요", "sentence": null, "request_id": null}]}
```

**발송을 막는 조건.** 아래 조건 가운데 하나라도 걸리면 반 알림장 보내기(3.6)는 알림장을 하나도 보내지 않는다. 시험은 `tests/integration/api/test_daily_notes.py`와 `tests/integration/db/test_daily_notes_runner.py`에 있다. 표에 적은 앞 파일의 시험은 모의·DB 두 모드에서 모두 돈다.

| 조건 | 응답 | 시험 |
| --- | --- | --- |
| 초안 작업이 `queued`·`running`·`failed`임 | 409 `NOTE_BATCH_BLOCKED`, `details.blocked = []` | `test_unfinished_batch_cannot_send`, `test_failed_writer_job_is_queryable_without_partial_notes` |
| 확인하지 않은 알림장(`ready`가 아님)이 있음 | 409 `NOTE_BATCH_BLOCKED`. 확인 항목이 없어도 확인하지 않은 알림장은 모두 `blocked[]`에 들어간다 | `test_batch_atomic_patch_and_parent_visibility` |
| 해결하지 않은 확인 항목이 있음 | 항목이 남아 있으면 확인(3.21의 `confirm`)부터 409 `INVALID_TRANSITION`이라 `ready`가 될 수 없다. 그래서 발송도 위 조건으로 막히고, 남은 항목은 `blocked[].open_checks`에 보인다 | `test_batch_atomic_patch_and_parent_visibility` |
| 아이 한 명의 초안이 실패함 | 그 아이의 `draft_failed` 항목 때문에 위 조건으로 막힌다 | `test_one_child_failure_keeps_other_children_and_blocks_batch`(DB) |
| 이미 보낸 알림장 | 막지 않는다. 다시 보내지 않고 `sent_count`에서도 뺀다. 같은 반을 한 번 더 보내면 200 `{"sent_count": 0}`이다 | `test_batch_atomic_patch_and_parent_visibility` |

```json
{"error": {"code": "NOTE_BATCH_BLOCKED", "message": "확인이 안 끝난 알림장이 있어요.", "trace_id": "…",
  "details": {"blocked": [{"note_id": "…", "child_id": "00000000-0000-4000-8000-000000000501", "open_checks": [{"id": "c1", "item_key": "supplies", "kind": "date_check", "problem": "준비물 날짜를 확인해 주세요", "sentence": "내일 실내화"}]},
                          {"note_id": "…", "child_id": "00000000-0000-4000-8000-000000000503", "open_checks": [{"id": "request-00000000-0000-4000-8000-00000000070a", "item_key": "pickup", "kind": "request_missed", "problem": "보호자 요청을 초안에 반영해 주세요", "sentence": null, "request_id": "00000000-0000-4000-8000-00000000070a"}]},
                          {"note_id": "…", "child_id": "00000000-0000-4000-8000-000000005401", "open_checks": []}, …]}}}
```


**④ 실제 모델 실측 (강사 2차 의견 API 1).** 팀 서버에서 실제 모델로 한 반을 처음부터 끝까지 돌렸다. 순서는 [알림장 시연 리허설](알림장_시연_리허설.md)과 같고, `tools/rehearse_daily_note.py`가 담임 입력 → 진행 조회 → 아이별 초안 → 담임 수정·확인 → 반 발송 → 학부모 조회를 차례로 부른다. 실행 전에 `python -m db.seeds.demo --refresh-note-requests`로 보호자 요청을 그날로 옮겼다.

| 항목 | 값 |
| --- | --- |
| 실행 | 2026-11-24 14:45:56~14:46:17 KST, 팀 서버 접속 주소, `--remote-ok` |
| 시연 커밋 | develop `97fda0b`(alembic `0011`). 시연 전에 다시 배포하면 같은 명령으로 다시 돌려 이 줄을 고친다 |
| 모델 | `DAILY_NOTE_WRITER=graph`, 자료 AI·검사 AI 모두 `LLM_MODEL_DEFAULT=gpt-6-luna`(역할별 값 비움), 작성기 제한 300초 |
| 아이 수 | 별빛반 20명(메모 있는 아이 17명) |
| 소요 시간 | 초안 작업 17초(작업자 `daily_note_drafts` 16.8초), 담임 입력부터 학부모 수신까지 21초 |
| 실패 | 작업 실패 0, 사람에게 넘김(`draft_failed`·`check_failed`) 0 |
| 확인 항목 | 5명 `needs_check`: 하늘 `date_check`·`sensitive`, 아라 `sensitive`, 윤슬 `sensitive`, 지아 `sensitive` 2개(1개는 투약 요청 코드 검사), 지안 `other_child`. 15명 `draft` |
| 발송 막힘 | 지아를 확인하기 전 반 발송은 409 `NOTE_BATCH_BLOCKED`(`blocked`에 지아만). 지아의 항목을 모두 풀어도 확인 전이면 409. 확인 뒤 200 `sent_count=20`, 확인 카드 `done` |
| 학부모 쪽 | `parent01`이 하늘 알림장(`sent`)을 받았고, 담임이 고친 줄이 그대로 보였다. 알림 1건 |

초안 저장 뒤 같은 기관·반·아이의 당일 보호자 투약·귀가가 새로 접수되면 기존 본문은 유지하고 `request_missed` 확인 항목을 해당 `request_id`와 함께 붙인다. `draft`·`needs_check`는 `needs_check`가 되고, `ready`도 확인자·확인 시각을 비우고 `needs_check`로 돌아간다. 이미 `sent`면 내용·확인 항목·상태는 유지한다. 두 경우 모두 반 카드 담당자에게 기존 `new_card` 알림을 보내며 `subject_type=daily_note`·`subject_id=아이 알림장 ID`로 알림장 화면에 연결하고, 같은 요청 재전송에는 확인·알림을 늘리지 않는다. 본문과 알림 제목에 보호자 원문을 복사하지 않는다. 다른 날짜·다른 반과 문의·상담·민원은 이 처리에서 제외한다. 작성기가 입력을 읽은 뒤 저장하기 전 접수된 요청도 저장 직전 다시 읽어 `request_missed`로 남긴다.

### 3.20 알림장 보기 — `GET /api/v1/daily-notes`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 날짜를 정해 아이별 알림장을 본다. 담임은 반 전체의 초안과 확인 상태를, 학부모는 이미 보낸 내 아이 알림장을 받는다(FR-10). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | date(필수), classroom_id(담임 필수), page·size·sort. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 학부모는 내 아이의 sent 알림장만, 담임은 현재 담당 반만 본다. director는 기관 전체를 읽으며 반을 고를 수도 있다. |
| ⑥ 정상 응답 | 200 + 쪽 나눈 items[]. 조건에 맞는 알림장이 없으면 빈 목록. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 학부모가 classroom_id를 보내더라도 내 아이·sent 조건을 먼저 적용한다. created_at으로 정렬한 다음 쪽을 나눈다. 모의 초안은 day·supplies·meal 줄에 아이 메모와 그날의 보호자 요청 줄을 더하고, 첫 아이의 준비물 확인 c1과 노을의 고정 귀가 요청이 빠졌다는 확인을 남긴다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `date` | 쿼리 | date | 필수 | 불가 | YYYY-MM-DD, 미래 날짜 조회도 허용 | 알림 날짜 |
| `classroom_id` | 쿼리 | string(UUID) | 담임 필수 | 생략 가능 | 담임은 현재 담당 반 | 학부모·원장은 선택 |
| `page`·`size` | 쿼리 | integer | 선택 | 불가 | 기본 1·20, page ≥ 1, size 1~100 | 쪽 나누기 |
| `sort` | 쿼리 | string | 선택 | 불가 | `-created_at`(기본)·`created_at` | 내림차순·오름차순 |
| `items[].id`·`child_id`·`note_date`·`status` | 응답 | UUID·date·string | 항상 | 불가 | draft·needs_check·ready·sent | 아이별 알림장; 보낸 것만 학부모에게 노출 |
| `items[].input_id` | 응답 | UUID | 항상 | 불가 | 해당 알림장의 daily_note_inputs.id | 담임 입력 묶음 ID. 별도 제출 없이 작업 상태 조회·재생성에 사용 |
| `items[].content`·`open_checks[]` | 응답 | object·object[] | 항상 | 빈 목록 가능 | 줄·출처·확인 항목 모양은 3.7 참고 | items는 key·label·value·source를 가짐 |
| `items[].open_checks[].kind` | 응답 | string | 항목마다 | 불가 | not_in_memo·sensitive·other_child·date_check·absent·draft_failed·check_failed·request_missed·return_limit | `return_limit`은 AI 수정 한도 초과로 담임 확인이 필요함 |
| `items[].confirmed_at`·`sent_at` | 응답 | datetime | 항상 | null 가능 | 확인·발송 뒤 시각 | 아직 실행하지 않았으면 null |
| `items[].version` | 응답 | integer | 항상 | 불가 | 1 이상, 기본 1 | 정정용 판. 3.30 정정 성공마다 1 증가하며, 발송 전 수정·확인·재생성·발송에서는 유지 |
| `items[].corrected_at` | 응답 | datetime | 항상 | null 가능 | 마지막 정정 시각 | 아직 정정하지 않았으면 null. 학부모 응답에도 포함 |
| `total`·`page`·`size` | 응답 | integer | 항상 | 불가 | 전체 건수·요청한 쪽·크기 | 목록 공통 칸 |

```http
GET /api/v1/daily-notes?classroom_id=00000000-0000-4000-8000-000000000101&date=2026-11-18
HTTP/1.1 200 OK
{"items": [{"input_id": "00000000-0000-4000-8000-000000000a01", "child_id": "00000000-0000-4000-8000-000000000503", "note_date": "2026-11-18", "status": "draft", "content": {"items": [{"key": "day", "label": "오늘 하루", "value": "블록 놀이와 산책을 했어요.", "source": {"type": "teacher_input", "document_id": null, "document_title": null, "request_id": null}}, {"key": "supplies", "label": "준비물", "value": "내일 실내화", "source": {"type": "teacher_input", "document_id": null, "document_title": null, "request_id": null}}, {"key": "meal", "label": "식사", "value": "점심: 카레라이스, 채소와 과일", "source": {"type": "document", "document_id": "00000000-0000-4000-8000-000000000b01", "document_title": "가상 식단표", "request_id": null}}]}, "open_checks": [], "confirmed_at": null, "sent_at": null}], "total": 20, "page": 1, "size": 20}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 422 | `VALIDATION_FAILED` | date 누락·날짜/UUID/쪽 형식 오류·담임의 classroom_id 누락 |

### 3.21 알림장 고치기·확인 — `PATCH /api/v1/daily-notes/{note_id}`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임이 아이별 알림장을 고치고 확인 항목을 해결한 뒤 발송 준비를 마친다(FR-10). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: application/json`. |
| ③ 경로·쿼리 | note_id(UUID, 필수). |
| ④ 요청 본문 | content·resolved_checks·confirm, 모두 선택. |
| ⑤ 검증·권한 | teacher만, 현재 담당 반 알림장만 고칠 수 있다. 출처인 문서와 요청도 범위를 검사해서, 요청의 child_id가 알림장의 아이와 다르거나 문서 visibility가 parents·all이 아니면 422 VALIDATION_FAILED다. sent 알림장은 이 PATCH로 수정할 수 없다. 보낸 뒤에는 이유와 판을 받는 정정 API(3.30)를 쓴다. 없는 확인 ID를 보내거나 미해결 항목을 남긴 채 confirm하는 경우는 저장된 확인 항목과 대조해야 알 수 있으므로 서버가 409로 막는다(4.1). |
| ⑥ 정상 응답 | 200 + note. confirm=true이고 미해결 항목이 0개면 ready로 바꾸고 confirmed_at을 남긴다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | content를 보내면 내용 전체를 새로 바꾼다. confirm=false(기본)이면 기존 확인을 지우고, 미해결 항목 유무에 따라 needs_check나 draft로 되돌린다. 빈 본문을 보내도 기존 확인은 풀린다. 오류가 나면 아무것도 수정하지 않는다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `note_id` | 경로 | string(UUID) | 필수 | 불가 | 현재 담당 반 알림장 | 3.20 응답에서 받은 ID |
| `content` | 본문 | object | 선택 | null 가능 | items[]의 key·label·value·source는 3.7; 빈 items도 허용 | 생략·null이면 내용 유지 |
| `content.items[].key` | 본문 | string | 줄마다 필수 | 불가 | day·meal·medication·pickup·supplies·child·inquiry | 줄 종류. child의 출처는 teacher_input, inquiry는 request만 허용 |
| `content.items[].label`·`value` | 본문 | string | 줄마다 필수 | value만 빈 문자열 가능 | label은 1자 이상, value 길이 제한 없음 | 줄 이름과 내용 |
| `content.items[].source` | 본문 | object | 줄마다 필수 | 불가 | document면 document_id·document_title, request면 request_id 필수 | 출처 종류는 teacher_input·document·request |
| `note.open_checks[].kind` | 응답 | string | 항목마다 | 불가 | not_in_memo·sensitive·other_child·date_check·absent·draft_failed·check_failed·request_missed·return_limit | `return_limit`도 남아 있으면 `confirm=true`는 409 |
| `resolved_checks[]` | 본문 | string[] | 선택 | 빈 목록 가능 | 기본 [], 현재 open_checks의 id만 | 해결한 확인 항목 |
| `confirm` | 본문 | boolean | 선택 | 불가 | 기본 false | 미해결 항목이 없어야 true 가능 |
| `note` | 응답 | object | 항상 | 불가 | 3.20 items[]와 같은 모양 | status·open_checks·confirmed_at 포함 |

```http
PATCH /api/v1/daily-notes/{note_id}
{"resolved_checks": ["c1"], "confirm": true}
HTTP/1.1 200 OK
{"note": {"child_id": "00000000-0000-4000-8000-000000000501", "status": "ready", "open_checks": [], "confirmed_at": "2026-11-18T10:00:00+09:00"}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `INVALID_TRANSITION` | sent 수정, 없는 resolved_checks ID, confirm인데 미해결 항목 있음(details.open_checks) |
| 422 | `VALIDATION_FAILED` | 형식·출처 필수 칸, 다른 아이·아이 없는 요청 출처, visibility가 staff인 문서 출처 |

### 3.22 자료 올리기 — `POST /api/v1/documents`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 교직원이 자료 파일과 적용 범위를 올리고 적재 결과를 확인한다(FR-13). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장), `Content-Type: multipart/form-data; boundary=…`. |
| ③ 경로·쿼리 | 없음. |
| ④ 요청 본문 | 아래 multipart/form-data 필드 표. classroom_ids[]는 같은 이름으로 여러 번 보낸다. |
| ⑤ 검증·권한 | teacher·director만 호출할 수 있다. 대상 반과 이전 문서가 범위 안에 있는지 검사하고, 새 판으로 올릴 때 이전 문서는 active여야 한다. |
| ⑥ 정상 응답 | 새 자료면 202 + document, 같은 기관에 바이트까지 같은 자료가 이미 있으면 200 + 기존 document를 돌려준다. 다만 DB 모드에서 그 기존 자료가 적재에 실패한 상태라면, 같은 ID로 다시 적재하고 202를 돌려준다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 적재가 성공했는지 실패했는지는 접수한 뒤 GET /documents/{document_id}(3.23)로 확인한다. 두 모드 모두 접수 요청 안에서 적재를 끝내므로, 202 응답의 ingest_status는 succeeded나 failed다. 이전 자료는 새 판이 적재에 성공했을 때만 superseded로 바꾼다. 새 판의 적재가 실패하면 옛 판을 그대로 쓰고 supersedes_id도 비운다. 두 모드가 같은 함수로 파일의 글을 추출한다. 모의 적재는 추출한 글을 500자씩 나눈다(빈 UTF-8 글 파일도 1조각). 파일명에 [실패]가 들어 있으면 ingest_status=failed·chunk_count=0으로 끝난다. DB 모드는 추출 뒤 기존 파싱·충돌 검사·임베딩 흐름을 따른다. 그 결과는 아래 'DB 모드 적재 결과' 표에 있다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `file` | 폼 | binary | 필수 | 접수는 빈 파일 허용 | 2MiB(2,097,152바이트) 이하. DOCX·HWPX는 압축 해제 총량도 같은 상한 | title은 파일명, 파일명이 없으면 자료. .md·.markdown·.txt(UTF-8)·.pdf·.docx·.hwpx의 글을 추출한다. HWP·글 없는 PDF·DOCX·HWPX·미지원 형식은 failed가 된다 |
| `doc_type` | 폼 | string | 필수 | 불가 | notice·schedule·menu·policy·consult_timetable·law·public_data | 자료 유형 |
| `visibility` | 폼 | string | 필수 | 불가 | staff·parents·all | 공개 범위 |
| `classroom_ids[]` | 폼 | string[](UUID) | 선택 | 생략 가능 | 기본 [], 담임은 현재 담당 반 | 비우면 원 전체 |
| `effective_from` | 폼 | date | 필수 | 불가 | YYYY-MM-DD, 미래 날짜 허용 | 적용 시작일 |
| `replaces_document_id` | 폼 | string(UUID) | 선택 | 생략 가능 | 범위 안의 active 문서 | 이전 판 |
| `document` | 응답 | object | 항상 | 불가 | 전체 칸은 3.23 참고 | ID·적재 상태·조각 수·error |

아래 예시는 200을 돌려준다. 올린 파일이 시드 식단표와 바이트가 같기 때문이다. 중복 여부는 같은 기관 안에서 파일 바이트의 SHA-256만 비교해 판단하므로, 이름·유형·공개 범위가 달라도 기존 자료를 돌려준다. 두 모드 모두 대상 반·이전 자료·기존 자료의 접근 범위를 먼저 확인한 뒤, 같은 바이트인 기존 자료를 200으로 돌려주는 검사를 이전 판의 active 상태 검사보다 먼저 한다. 따라서 이미 superseded·conflict_pending인 이전 판을 지정해도 같은 바이트면 200이며, 다른 바이트로 새 판을 만들 때는 409 INVALID_TRANSITION이다. DB에서 failed 자료를 다시 적재하는 경우는 앞의 202 예외이며 이때는 이전 판이 active여야 한다. 예시의 multipart 각 부분은 이름·값을 줄여 적었다.

```http
POST /api/v1/documents
Content-Type: multipart/form-data; boundary=demo
[file: filename="식단표.txt", Content-Type: text/plain, 내용="점심: 카레라이스, 채소와 과일"]
[doc_type=menu, visibility=all, effective_from=2026-11-18]
HTTP/1.1 200 OK
{"document": {"id": "00000000-0000-4000-8000-000000000b01", "title": "가상 식단표", "ingest_status": "succeeded", "effective_from": "2026-11-08", "chunk_count": 1}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 409 | `INVALID_TRANSITION` | 이전 문서가 active가 아님 |
| 413 | `VALIDATION_FAILED` | 파일이 2MiB를 넘음 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |

**DB 모드 적재 결과.** DB 모드는 글을 `## ` 제목 단위로 나누고, 그 제목을 근거 위치(location)로 쓴다. 제목이 없는 글은 본문 전체가 한 조각이 되고, 위치는 '본문'이다. 적재에 실패하면 이유와 상관없이 error.code는 `UPSTREAM_UNAVAILABLE`이다. 실패 이유는 error.message로 구분한다. 기존 동작은 2026-11-23 develop `24258f2`의 직접 업로드로 확인했고, PDF·DOCX·HWPX 확장은 표에 적은 mock·DB 통합 시험으로 확인한다.

| 올린 파일 | 결과 | error.message와 남는 값 | 시험 |
| --- | --- | --- | --- |
| .pdf·.docx·.hwpx(대소문자 무관) | 202 · succeeded | PDF는 pypdf, DOCX는 python-docx로 본문 문단·표를 순서대로 읽는다. HWPX는 표준 zipfile·XML로 Contents/sectionN.xml의 문단 글자를 번호 순으로 읽는다. 추출 뒤 DB 파싱·충돌 검사·임베딩 흐름은 그대로다 | `test_document_upload_formats_store_text_and_dedupe`, `test_document_upload_formats_reuse_conflict_parsing` |
| 옛 .hwp, 추출한 글이 없는 PDF·DOCX·HWPX(스캔본 포함) | 202 · failed · chunk_count 0 | "한글에서 hwpx나 PDF로 저장해 올려 주세요". OCR은 하지 않는다. 모의 모드도 같은 안내 | `test_upload_unreadable_file_fails_with_message`, `test_document_upload_formats_failure_events` |
| 지원하지 않는 다른 확장자 | 202 · failed · chunk_count 0 | "지금은 .md·.txt·.pdf·.docx·.hwpx 글 파일만 읽을 수 있어요" | `test_document_upload_formats_failure_events` |
| 깨진 PDF·DOCX·HWPX | 202 · failed · chunk_count 0 | "자료를 읽지 못했어요." | `test_document_upload_formats_failure_events` |
| DOCX·HWPX의 모든 ZIP 항목 압축 해제 크기 합계가 2MiB 초과 | 202 · failed · chunk_count 0 | "자료 파일은 2MiB 이하여야 해요." 글을 읽기 전에 거절하며 모의 모드도 같다 | `test_document_upload_formats_archive_total_limit` |
| UTF-8로 읽히지 않는 글 | 202 · failed | "UTF-8 글 파일이 아니에요" | 직접 호출로만 확인 |
| 빈 파일, 공백·빈 줄만 있는 파일 | 202 · failed | "읽을 내용이 없어요". 모의 모드에서는 1조각으로 succeeded가 된다 | 직접 호출로만 확인 |
| 맨 앞이 `---`로 시작함 | 머리말로 읽어 본문과 떼어 낸다 | 필수 키 6개(title·doc_type·kindergarten_id·effective_from·visibility·source)가 빠지거나 값이 허용 범위 밖이면 failed가 된다("머리말에 필수 값이 없습니다: …", "머리말이 닫히지 않았습니다" 등). 통과해도 자료 이름·유형·공개 범위·적용일은 폼 값을 쓴다 | `test_upload_conflicting_notice_is_pending_with_conflicts`, `test_bad_front_matter_is_rejected`(단위 시험) |
| 사용 중인 다른 자료와 같은 항목의 날짜·숫자가 다름 | 202 · succeeded · conflict_pending | conflicts[]에 충돌 항목을 담는다. 새 판으로 올렸어도 옛 판은 active로 두고 supersedes_id를 비운다. 사람이 확인하기 전에는 근거 검색에 나오지 않는다 | `test_upload_conflicting_notice_is_pending_with_conflicts` |
| 충돌 없는 새 판(replaces_document_id) | 202 · succeeded · active | supersedes_id에 옛 판 ID가 들어가고, 옛 판은 superseded가 된다 | `test_upload_plain_text_new_version_supersedes_old` |
| 같은 기관에 바이트가 같은 자료가 있음 | 200 · 기존 자료 | 접근 범위 확인 뒤 이전 판 상태 검사보다 먼저 돌려준다. 새 행·조각·메타데이터를 만들거나 바꾸지 않으며 기존 자료나 지정 이전 판이 superseded·conflict_pending이어도 같다 | `test_upload_conflicting_notice_is_pending_with_conflicts`, `test_document_duplicate_precedes_replacement_state_check` |
| 적재에 실패했던 자료와 바이트가 같음 | 202 · 같은 ID로 다시 적재 | title을 새 파일명으로 바꾼다. 두 요청이 겹치면 한쪽만 적재하고, 늦은 쪽은 200을 받는다 | `test_upload_unreadable_file_fails_with_message`, `test_failed_reupload_runs_once_when_two_requests_race` |
| 2MiB를 넘음 | 413 · `VALIDATION_FAILED` | "자료 파일은 2MiB 이하여야 해요." 자료 행을 만들지 않는다 | `test_upload_duplicate_class_and_size_limit` |

충돌은 모델을 부르지 않고 규칙으로 찾는다. 목록 줄과 표 줄에 적힌 날짜, 그리고 목록 줄에서 ℃·원·분·명이 붙은 숫자를 항목 이름별로 모은다. 비교 대상은 같은 기관에서 사용 중(active)이고 적재가 끝난 다른 자료다. 새 판이 대신할 옛 판은 여기서 뺀다. 항목 이름이 같고 대상 반이 겹치는데 값이 다르면 충돌로 본다. 다만 식단표·상담 시간표(menu·consult_timetable)는 날짜를 비교하지 않는다. 충돌 항목 하나는 아래와 같은 모양이다(DB 모드, 시드 '겨울방학 안내'와 날짜가 다른 글을 올림).

```json
{"label": "겨울방학", "kind": "date", "value": "2026-12-26~2027-01-03", "location": "1쪽 겨울방학 기간",
 "other_document_id": "…", "other_document_title": "겨울방학 안내", "other_location": "1쪽 겨울방학 기간", "other_value": "2026-12-24~2027-01-03"}
```

### 3.23 자료 목록·상세 — `GET /api/v1/documents`, `GET /api/v1/documents/{document_id}`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 교직원이 자료 목록과 자료별 적재 상태·오류를 본다(FR-13). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 목록은 page·size·sort, 상세는 document_id(UUID). |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | teacher·director만 볼 수 있다. 같은 기관 안에서 원 전체 자료와 현재 담당 반이 대상인 자료를 보며, 원장은 반 제한 없이 본다. visibility 값은 교직원 조회를 막지 않는다. |
| ⑥ 정상 응답 | 목록은 200 + items[]·total·page·size, 상세는 200 + document. 적재에 실패한 자료도 조회는 200이다. |
| ⑦ 오류 응답 | 아래 오류 표. |
| ⑧ 실행 규칙 | 목록은 생성 시각으로 정렬한 뒤 쪽을 나눈다. 두 모드 모두 superseded 자료도 목록에 남긴다. status와 ingest_status는 서로 따로 바뀌므로, 적재에 실패한 파일도 status=active일 수 있다. 모의 구현에서 conflicts는 늘 []다. DB 모드는 충돌 항목(3.22)을 상세에만 담고, 목록 items[]의 conflicts는 []로 둔다. 두 모드 모두 목록·상세의 error는 현재 ingest_status가 failed일 때만 가장 최근 실패의 {code, message}를 주고 queued·running·succeeded일 때는 null이다. 실패 뒤 다시 적재해 성공하면 과거 실패 이력은 보존하되 현재 error는 null이다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `document_id` | 상세 경로 | string(UUID) | 필수 | 불가 | 조회 범위 안 | 접수 응답의 document.id |
| `page`·`size` | 쿼리 | integer | 선택 | 불가 | 기본 1·20, page ≥ 1, size 1~100 | 쪽 나누기 |
| `sort` | 쿼리 | string | 선택 | 불가 | `-created_at`(기본)·`created_at` | 내림차순·오름차순 |
| `document.id`·`title`·`doc_type`·`visibility`·`classroom_ids[]` | 상세 응답 | UUID·string·UUID[] | 항상 | 빈 classroom_ids 가능 | 목록 items[]도 같은 모양 | 자료 이름·종류·공개 범위·대상 반 |
| `document.effective_from`·`effective_to`·`supersedes_id` | 상세 응답 | date·UUID | 항상 | effective_to·supersedes_id는 null 가능 | 새 판에만 이전 문서 ID | 적용 기간·판 연결 |
| `document.status`·`ingest_status` | 상세 응답 | string | 항상 | 불가 | status는 모의 구현에서 active·superseded이고 DB 모드는 conflict_pending도 쓴다. ingest_status는 queued·running·succeeded·failed | 사용 상태·적재 진행 |
| `document.chunk_count`·`conflicts[]`·`error` | 상세 응답 | integer·object[]·object | 항상 | error는 null 가능 | 조각 수, 오류는 {code, message}, 충돌 항목 모양은 3.22 | 실패면 code는 UPSTREAM_UNAVAILABLE이고 이유는 message에 있다(3.22 DB 모드 적재 결과). 충돌 판별은 모의 구현에 없음 |
| `document.chunks[]` | GET 상세 응답만 | object[] | 항상 | 조각이 없으면 [] | index 오름차순. 목록·업로드 응답에는 없음 | 교직원이 읽을 원문 조각. 검색에서 제외하는 의심 조각도 숨기지 않음 |
| `document.chunks[] { index, location, content, suspicious }` | GET 상세 응답만 | integer·string·string·boolean | 항상 | location은 null 가능 | index는 0부터인 조각 순번, location은 근거 위치, content는 저장된 원문 | suspicious는 `agents.guardrails.injection.suspicious_chunk(content)` 판정. true면 검색에서 제외되는 모델 지시 의심 조각 |
| `total`·`page`·`size` | 응답 | integer | 항상 | 불가 | 전체 건수·요청한 쪽·크기 | 목록 공통 칸 |

```http
GET /api/v1/documents?size=1
HTTP/1.1 200 OK
{"items": [{"id": "00000000-0000-4000-8000-000000000b01", "title": "가상 식단표", "status": "active", "ingest_status": "succeeded"}], "total": 3, "page": 1, "size": 1}
GET /api/v1/documents/00000000-0000-4000-8000-000000000b01
HTTP/1.1 200 OK
{"document": {"id": "00000000-0000-4000-8000-000000000b01", "title": "가상 식단표", "doc_type": "menu", "visibility": "all", "classroom_ids": [], "effective_from": "2026-11-08", "effective_to": null, "status": "active", "ingest_status": "succeeded", "supersedes_id": null, "conflicts": [], "chunk_count": 1, "error": null, "chunks": [{"index": 0, "location": "1쪽", "content": "가상 식단 안내", "suspicious": false}]}}
```

| HTTP | `code` | 조건 |
| --- | --- | --- |
| 401 | `UNAUTHENTICATED` | 토큰 없음·만료·무효 |
| 403 | `FORBIDDEN_ROLE` | 허용하지 않은 역할 |
| 404 | `NOT_FOUND` | 없거나 기관·반·소유 범위 밖 |
| 422 | `VALIDATION_FAILED` | 필수 칸·타입·허용 값·길이가 맞지 않음 |


### 3.24 반 아이 목록 — `GET /api/v1/classrooms/{classroom_id}/children`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 알림장 메모를 쓸 아이를 이름순으로 고른다(FR-10). |
| ② 요청 헤더 | `Authorization`(필수), `X-Request-ID`(권장). |
| ③ 경로·쿼리 | 경로 classroom_id(UUID, 필수)만 받는다. 페이지 쿼리는 없다. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 현재 배정 기간 안에 있는 담임과 같은 기관 원장만 볼 수 있다. 학부모가 부르면 403 FORBIDDEN_ROLE, 없는 반이나 범위 밖 반이면 404 NOT_FOUND다. |
| ⑥ 정상 응답 | 200 + `{ items: [{ id, display_name, classroom_id, profile_photo }] }`. 이름 오름차순이고, 아이가 없으면 items는 []다. profile_photo는 사진이 없으면 null이다(3.41). |
| ⑦ 오류 응답 | 401 UNAUTHENTICATED, 403 FORBIDDEN_ROLE, 404 NOT_FOUND, UUID 형식이 틀리면 422 VALIDATION_FAILED. |
| ⑧ 실행 규칙 | 요청할 때마다 담임 배정 기간과 기관을 확인한다. 보호자·계정 정보는 보내지 않는다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| `classroom_id` | 경로 | string(UUID) | 필수 | 불가 | 볼 수 있는 반 | 목록을 받을 반 |
| `items[]` | 응답 | object[] | 항상 | 빈 목록 가능 | display_name 오름차순 | 해당 반 아이 전부 |
| `items[].id`·`classroom_id` | 응답 | string(UUID) | 항상 | 불가 | 아이 ID·반 ID | id는 child_memos의 child_id로 보냄 |
| `items[].display_name` | 응답 | string | 항상 | 불가 | 아이 표시 이름 | 목록에 보여 줄 이름 |
| `items[].profile_photo` | 응답 | object 또는 null | 항상 | null 가능 | `{file_url}` | 아이 프로필 사진(API 75 주소). 내 정보·로그인의 `children[]`에도 같은 필드가 있다 |

```http
GET /api/v1/classrooms/00000000-0000-4000-8000-000000000102/children
HTTP/1.1 200 OK
{"items": [{"id": "00000000-0000-4000-8000-000000000502", "display_name": "바다", "classroom_id": "00000000-0000-4000-8000-000000000102", "profile_photo": {"file_url": "/api/v1/children/00000000-0000-4000-8000-000000000502/profile-photo"}}]}
```

### 3.25 내 AI 기억 보기·지우기 — `GET /api/v1/memories`, `DELETE …/memories/{memory_id}`

내가 알려 준 내용을 직접 보고 지워 다음 처리부터 쓰지 않게 하는 API예요. 세 역할이 자기 기억을 보고, 학부모는 자기 선호와 현재 보호자 관계가 있는 아이의 돌봄 메모(pending 포함)를 본다. 담임은 본인 기억과 본인이 승인한 답·본인 규칙을 본다. 원장은 본인 기억만 본다. 다른 가정·기관의 기억과 삭제한 기억은 보이지 않으며, 범위 밖 삭제·확인은 404와 거부 이력을 남긴다.

| 필드 | 위치 | 타입·규칙 | 뜻 |
| --- | --- | --- | --- |
| `kind` | 쿼리, 선택 | rejection_reason·preference·tone·care_note·saved_answer·rule | 생략하면 볼 수 있는 모든 종류 |
| `page`·`size`·`sort` | 쿼리 | 공통 목록 규칙, created_at·-created_at | 종류를 합친 뒤 쪽 나누기 |
| `items[].id` | 응답 | 기억은 양의 정수, 승인 답·규칙은 UUID | 원 항목 ID 유지 |
| `items[].kind`·`title`·`content`·`reason_code`·`structured`·`created_at` | 응답 | 종류·한 줄 제목·내용·이유 코드(null 가능)·구조화 값·생성 시각 | 기존 칸에 title만 추가 |
| `items[].child_id`·`child_name` | 응답 | UUID·string 또는 null | 돌봄 메모의 아이 |
| `items[].confirm_status`·`confirmed_at` | 응답 | pending·confirmed·discarded, date-time 또는 null | 보호자가 기억해 달라고 한 시각 |
| `items[].source` | 응답 | memory·saved_answer·rule | 원 종류 |
| `saved_answers[]` | 응답 | id·question·answer·status·approved_at | 담임 본인이 승인한 답, 다른 역할은 빈 목록 |
| `rules[]` | 응답 | id·reason_code·rule_text·status | 담임 본인의 proposed·active·off·declined 규칙, 다른 역할은 빈 목록 |
| `total`·`page`·`size` | 응답 | 정수 | 범위·종류로 거른 뒤 쪽 나누기 |

DELETE는 본인 기억과 학부모의 자기 아이 돌봄 메모만 지우며 성공은 204다. content와 structured를 비우고 deleted_at을 남겨 이후 모든 작성 입력에서 제외한다. 승인 답과 규칙의 UUID는 이 삭제 주소에 보내지 않는다. 화면은 `items[].source`로 버튼 주소를 고른다.

| `source` | 화면 버튼 | 주소 |
| --- | --- | --- |
| `memory` | 지우기 | `DELETE /memories/{id}` (정수 id). 돌봄 메모 pending은 API 67로 기억·버리기 |
| `saved_answer` | 끄기·다시 켜기 | API 69 `PATCH /saved-answers/{id}` `{status:"off"\|"active"}` |
| `rule` | 끄기 | 3.17 `POST /memory-rules/{id}/decision` `{decision:"off"}`. 끈 규칙은 목록에 status off로 남고, 같은 이유 거절이 끈 뒤로 3번 더 쌓이면 새 제안 카드로 다시 묻는다(FR-20). 끈 규칙을 그대로 다시 켜는 주소는 없다 |

보호자 기억 후보(선호·돌봄 메모)는 보호자의 현재 약관 판 동의를 다시 확인한 뒤 만든다. `ai_processing`이 없으면 기억 추출 모델에 글을 보내지 않고, 돌봄 메모는 `child_info`·`child_health`까지 있어야 저장한다.

API 67 `POST /memories/{memory_id}/confirm`은 `{decision:"remember"|"discard"}`를 받는다. 그 아이 보호자만 pending 후보를 결정하며 다른 상태는 409 INVALID_TRANSITION이다. remember는 confirmed와 confirmed_at, discard는 discarded와 빈 content·structured를 남긴다. 응답은 `{id,confirm_status,confirmed_at}`다. 학부모 요청 상세 `GET /requests/{id}`의 `memory_candidates:[{id,child_name,content}]`에는 그 요청에서 생긴 pending만 들어간다(없거나 교직원이면 빈 목록). memory_candidate 앱 알림은 후보마다 한 번이고 원문은 알림에 싣지 않는다.

API 69 `PATCH /saved-answers/{answer_id}`는 `{status:"off"|"active"}`를 받는다. 승인한 담임 본인과 같은 기관 원장만 가능하다. 응답은 `{saved_answer:{id,question,answer,status,approved_at}}`다. off 답은 재사용하지 않아서 다음 문의도 새 근거와 카드로 확인한다. invalidated 답은 다시 켤 수 없고 409 INVALID_TRANSITION이다.

담임의 회신 카드 `edit_approve`가 커밋되면 API 백그라운드에서 원 초안·발송문을 비교한다. `LLM_MODEL_MEMORY`가 켜져 있을 때만 tone 후보 0~2개를 검사해 저장하며(80자 이하 한 문장, 이름 가림, 민감정보 형식·숫자 제외), 본인 tone은 최대 12개이고 같은 문장은 중복 저장하지 않는다. structured는 `{source: edit_approve, card_version: 승인 전 판}`이다. 실패는 memory/tool_failed 이력만 남기고 승인·발송 응답은 성공한다. 다음 문의·알림장 작성에 같은 원·담임의 최신 tone 8개를 표현 지침으로만 넘기며 목록·삭제 계약은 같다.

문의 approve·edit_approve 뒤 `EMBEDDING_MODEL`이 켜져 있으면 질문(아이 이름·민감정보 형식 가림)·실제 발송 답·승인자·요청 반·질문 벡터와 근거 문서를 saved_answers·saved_answer_sources에 저장한다. no_evidence·conflict·근거 0개는 직접 쓴 답도 저장하지 않는다. 같은 원의 원 전체 또는 같은 반 답 중 active이고 모든 근거 문서가 현재 유효·공개·반 허용인 답만 코사인 유사도 0.80 이상 상위 하나를 작성 AI의 prior_answer로 넘긴다. 표현 참고용이고 사실·검사는 새 chunks 인용만 따른다. 기존 문서 변경 트리거로 off 답까지 무효화하며 GET /memories에서 본인이 승인한 답의 상태를 본다.

아이 개인의 하루를 묻는 문의는 현재 보호자 관계가 맞는 아이의 최근 3일(오늘 포함) sent 알림장도 chunks 후보로 찾는다. 미발송·다른 아이·지난 날짜는 제외한다. 후보는 `{chunk_id:null,source:"daily_note",note_id,note_date,title:"M월 D일 알림장",quote}`이며 작성 입력에는 content·score도 있다. 인용은 note_id와 원문을 대조하고 검사 AI도 받는다. 개인 기억과 달리 실제 보낸 알림장은 사실 근거다. card_evidence.chunk_id는 NOT NULL이라 카드 상세의 `card.draft.note_evidence[]`에 이 목록을 보이고, 문서 evidence[]는 기존 모양을 유지한다. 수정 승인 뒤에도 목록을 유지한다. 일반 원 자료 질문은 기존 검색 그대로다. 아이 알림장이 들어간 답은 saved_answers에 저장하지 않는다.

아이의 몸·마음·친구·식사·낮잠을 묻는 문의는 같은 보호자 확인으로 질문이 가리키는 날(오늘·어제·그제, 날짜 말이 없으면 질문 받은 날)의 담임 관찰 기록(daily_records, 삭제 제외, 날마다 최근 3개)도 후보로 넣는다. 후보는 `{chunk_id:null,source:"daily_record",record_id,record_date,title:"M월 D일 관찰 기록",quote}`(민감정보 형식 가림)이고 카드 상세의 `card.draft.record_evidence[]`에 같은 방식으로 보인다. 관찰 기록은 보호자에게 바로 보이지 않는 메모라 담임 검토 초안에만 쓰고, 학부모 sources에는 넣지 않으며 saved_answers에도 저장하지 않는다.

### 3.26 알림장 다시 만들기 — `POST /api/v1/daily-notes/drafts/{input_id}/regenerate`

| 항목 | 내용 |
| --- | --- |
| ① 호출 목적 | 저장해 둔 반 입력으로 아직 확인하지 않은 초안만 다시 만든다. 실패하거나 중단된 입력도 이 API로 다시 시도한다. |
| ② 권한 | teacher가 현재 담당 반(대체 담임 배정 기간 포함)에 대해서만 호출한다. 다른 반·다른 기관의 입력이나 없는 입력은 404, 원장·학부모는 403이다. |
| ③ 경로·본문 | input_id는 UUID이고 본문은 없다. activities·supplies·child_memos는 저장된 입력을 그대로 쓰고, 보호자 요청과 식단은 실행할 때 다시 모은다. |
| ④ 정상 응답 | 202 + RegenerateResponse `{input_id, draft_status, error, kept_edited}`. kept_edited는 접수할 때 교사가 고쳐서 보존한 미확인 알림장 수(0 이상 정수)다. DB는 queued를 거쳐 running→succeeded 또는 failed로 가고, 모의는 결과를 바로 만든다. 진행과 결과는 API 23·24와 똑같이 조회하며, 기존 DraftResponse에는 kept_edited를 더하지 않는다. |
| ⑤ 차단 | 입력에 sent 알림장이 하나라도 있으면 409 INVALID_TRANSITION이다. 잠금은 발송과 같은 입력 잠금을 쓴다. |
| ⑥ 보존 | ready 알림장은 내용·확인자·시각·검사 항목을 그대로 둔다. draft·needs_check 알림장도 content ≠ ai_original이거나 daily_note_edited 이력이 있으면 모두 보존한다. 나머지는 새 초안, 새 확인 ID, 새 ai_original로 갱신하되 기존 알림장 ID는 유지한다. 실행하는 동안 생긴 수정·확인은 저장 직전에 다시 검사하고, 초안이 아직 없는 아이는 새로 저장한다. 전입 아이는 카드 목록·상세의 `note_batch.children[].status = missing`으로 먼저 보이며, 기존 아이가 모두 ready라면 보존 규칙에 따라 전입 아이만 새로 생성한다. |
| ⑦ 복구·동시성 | failed면 다시 접수한다. queued·running은 시작한 지 DAILY_NOTE_WRITER_TIMEOUT(기본 300초)이 지나지 않았으면 현재 상태만 돌려주고 작성기를 다시 부르지 않는다. 시작 시점은 반 묶음 카드의 draft.draft_started_at으로 판단하며, 대기 중이면 접수 시각, 실행 중이면 실행 시각이 담긴다. 이 기록이 없는 옛 입력은 created_at을 쓴다. 제한을 넘겼으면 다시 접수하고, 이전 실행이 늦게 낸 성공·실패는 버린다. 재생성 도중에 생긴 교사 수정·확인도 보존한다. |
| ⑧ 이력 | 이력은 아이별 events.daily_note_id에 연결한다. 처음 저장과 재생성 저장은 daily_note_drafted, 내용이 실제로 바뀐 PATCH만 daily_note_edited, 확인은 daily_note_confirmed, 보내기는 daily_note_sent다. 빈 PATCH나 확인 항목 해소만으로는 edited 이력을 남기지 않는다. 확인을 취소하면 기존 returned로 ready→draft를 남기고, 검사가 해소되어 needs_check→draft가 되면 기존 checked로 상태 변화를 남긴다. 재생성을 요청한 사람은 반 묶음 카드의 draft.regenerated_by와 새 drafted 이력의 detail.regenerated_by에 저장하며, 이 저장은 상태 변경과 같은 트랜잭션에서 한다. |

`daily_notes.ai_original`은 선생님이 마지막으로 받은 AI 초안이다. 선생님이 PATCH·확인·발송을 해도 바뀌지 않고, 수정하지 않은 미확인 알림장을 재생성해 저장할 때 새 초안으로 갱신된다. 기존 공개 NoteView에는 이 칸을 추가하지 않는다. 0003 이전 행은 마이그레이션 시점의 content로 채운다. 그 전에 사라진 초안까지 복원했다는 뜻은 아니다. 말투 규칙은 기억 AI가 이 원본과 수정 결과를 이용해 뽑고, 백엔드는 저장·조회·이력만 제공한다.

DB 그래프 실행은 writer·checker를 부르기 직전마다 입력 행의 `xmin`이 실행 토큰과 같은지 확인한다. 다시 만들기로 토큰이 바뀌면 옛 실행은 `Superseded`로 중단하고 작업 실패 이력을 남기지 않는다. 이미 시작한 모델 호출은 끝날 수 있지만 다음 그래프 모델 호출은 막으며, 저장 직전 토큰 검사도 유지한다. 대역 writer의 `write(payload)` 계약은 그대로다. 입력의 `roster_names`에는 보존할 아이를 포함한 현재 반 전체 이름을 넣고, `children`에는 이번에 쓸 아이만 넣는다. 대역은 전체 이름으로 다른 아이 이름을 검사한다. 그래프의 이름 검사에서 `roster_names`를 우선 읽는 연결은 그래프 담당 후속 작업이다. 반 공통 줄은 대역도 그래프의 같은 함수로 만들며, day(오늘 하루)·supplies(준비물)·meal(식사) 순서, 준비물 없음 생략, 해당 날짜 식단 추출을 공유한다. 실행 이력의 `trigger`·자동 재시도 횟수·큐 대기·아이별 복구 집계는 DB 설계서 2.6을 따른다.

### 3.27 [제안] 투약·귀가 요청

이 절은 투약·귀가 요청(3번의 투약·귀가 칸과 API 34~36·50~51)을 다룬다. FR-16·AC-09에 맞춰 미등록 인계자와 투약 필수값 누락을 표시한다. 투약 용량·시간과 인계자는 AI가 추측하지 않으며, 보호자 원문과 추가 대화를 그대로 보존한다.

| API | 입력 | 응답·권한 |
| --- | --- | --- |
| 기존 3 `POST /requests` | type에 medication·pickup도 받는다. body·child_id·client_request_id는 기존과 같다. pickup이면 pickup_guardian_id 또는 pickup_name·pickup_relation을, medication이면 medication_name·medication_dose·medication_time을 선택으로 보낸다. 문자열은 각각 100자 이하다. | 202 received. 같은 키로 다시 보내면 기존 요청과 현재 상태를 200으로 돌려준다. 자기 아이의 보호자만 등록할 수 있다. |
| 34 `GET /children/{child_id}/pickup-guardians` | 아이 UUID | 200 `{items:[{id,display_name}]}`, 이름순이다. 자기 아이의 보호자, 배정 기간 안의 담임, 같은 기관 원장만 읽을 수 있다. 연락처·로그인 ID는 보내지 않는다. |
| 35 `GET /care-requests` | classroom_id·status(received·assigned·completed·rejected)는 선택이다. page=1·size=20(최대 100)이고, sort는 -created_at(기본)·created_at·-updated_at·updated_at이다. | CareRequestList. 기존 RequestList 항목에 child_id(UUID)·child_name(string)·version·unregistered_pickup·missing_fields를 더한다. child_name은 children.display_name의 현재 이름이며 두 아이를 구분할 때 쓴다. 담임은 현재 반, 원장은 기관 전체를 본다. next_action은 confirm·complete·null 중 하나다. |
| 36 `POST /requests/{request_id}/care-decisions` | `{decision:"confirm"|"complete"|"reject", version:1, pickup_guardian_id?:UUID, reason_text?:string}` 형식이다. version은 필수이며 양의 정수다. | 200 `{request:{id,status},care:CareOut}`. 배정 기간 안의 담임과 같은 기관 원장만 실제 확인을 기록할 수 있다. |
| 50 `POST /requests/{request_id}/cancel` | 본문 없이 호출한다. | 200 `{request:{id,status},care:CareOut}`. 자기 투약·귀가 요청만 가능하며 completed·rejected면 409다. |
| 51 `PATCH /requests/{request_id}/care` | version(양의 정수)과 고칠 투약/인계자 칸을 하나 이상 보낸다. 생략한 칸은 유지하고 null은 비운다. | 200 `{request:{id,status},care:CareOut}`. 자기 요청의 received·assigned에서만 가능하다. |

등록 인계자는 같은 기관·같은 아이의 child_guardians에 연결된 활성 학부모 계정이다. 요청에 UUID를 명시했으면 접수할 때와 새로 confirm할 때 검사하고, 틀린 UUID는 422 VALIDATION_FAILED다. 등록 인계자로 확인하면 확인 당시의 UUID·이름·관계를 이력에 보존하므로, 그 뒤 계정이 비활성되거나 아이 연결이 해제되어도 complete를 막지 않는다. 등록 인계자의 confirm·complete에는 같은 pickup_guardian_id를 다시 보내고, 미등록이면 생략한다. reject는 인계자 UUID를 다시 요구하지 않는다. 현장 신원 확인은 교직원이 맡는다.

UUID 없이 이름·관계만 적은 요청도 접수·확인·완료할 수 있고, 기존 '오늘 할머니가 데리러 가요' 시드도 마찬가지다. 이때 상세 care와 교직원 목록의 unregistered_pickup은 true다. 이름·관계마저 없으면 null로 두고 원문을 보여 준다. 교직원이 confirm하는 것 자체가 명시 확인이다. 그래서 confirm하면 별도 checked 이력에 '미등록 인계자 확인'·실제 actor·version을 남기고, 원장에게 알림 1건을 만든다. 원장 경고는 같은 요청에서 인계자 이름·관계가 같으면 정정 후 다시 확인해도 한 번만 만들고, 이름이나 관계가 달라진 인계자는 새 경고 대상으로 본다.

투약 요청에 약 이름·용량·시간이 없거나 공백이어도 요청을 막지 않는다. 대신 medication_name·medication_dose·medication_time 중 빠진 칸을 missing_fields에 넣어 상세 request·care와 교직원 목록에 표시한다. 보호자 본문에서 수치를 뽑아 채우지는 않는다. 요청은 received와 확인 할 일을 그대로 유지하고, 교직원이 대화 전체와 누락을 확인한 뒤 결정한다. 원문만 있는 기존 시드는 투약 세 칸을 모두 누락으로 표시한다. 다른 유형에 투약·인계자 칸을 보내면 422다.

상태는 **received → assigned → completed**로 바뀐다. confirm은 내용을 확인하고 수행을 준비했다는 기록이고, complete는 실제로 투약·인계를 마쳤다는 기록이다. 확인하기 전에 complete를 보내면 409 INVALID_TRANSITION이다. 같은 입력 판에서 같은 단계를 다시 보내면 기존 결과만 돌려주고, 완료한 뒤의 confirm이나 대화 추가는 409다. 이 흐름은 AI 카드 승인이 아니므로 cards·approvals를 만들지 않으며, 실제 주체는 events.actor_type=user·actor_id다.

care.version은 입력 판이다. 처음은 1이고 **보호자 새 글이나 구조화 입력 수정마다 1씩 증가**한다. 확인·완료만으로는 판이 바뀌지 않는다. 교직원은 상세의 care.version이나 교직원 목록의 version을 결정에 담아 보낸다. 그 사이에 보호자 글이나 입력 수정이 왔으면 confirm·complete·reject와 입력 수정 모두 409 CARD_VERSION_CONFLICT와 details.current_version을 돌려준다.


보호자 글은 취소인지 정정인지 자동으로 판단하지 않고, 모두 다시 확인할 대상으로 삼는다. 요청이 assigned이면 received로 되돌리고 confirmed_at을 지운다. 이미 received여도 판을 올리고 담당자(없으면 원장)에게 알림 1건을 남긴다. 교직원은 새 대화 전체를 읽고 최신 판으로 다시 확인한다. 취소 글이 와도 요청 완료나 자동 취소로 처리하지 않으며, 원래 본문과 구조화 입력도 바꾸지 않는다. 새 글·확인·완료는 요청 행의 FOR NO KEY UPDATE 잠금으로 직렬화하고, 상태·이력·알림은 같은 트랜잭션에서 저장한다. 이 과정에서 AI는 실행하지 않는다.

교직원은 received·assigned에서 reject할 수 있다. reason_text는 1~1000자이며 공백뿐인 사유는 422다. 요청은 rejected가 되고 dismissed 이력에 care_decision=reject·reason_text·version·실제 행위자를 남긴다. 학부모에게 care_rejected 알림으로 사유를 전하고, 상세 rejection은 `{reason_code:"other",reason_text}`다. 반려·완료 뒤 재결정은 409다.

학부모의 명시적 취소는 API 50으로 한다. rejected와 cancelled 이력(detail.cancelled_by_parent=true)을 같은 트랜잭션에 저장하고, 담당자(없으면 원장)에게 cancelled 알림을 보낸다. 학부모 목록·상세·타임라인의 표시는 "취소함"이며, 교직원 목록에서도 구분한다. 요청 원문·추가 대화·확인 당시 인계자·입력 판은 보존한다. 추가 글에 "취소"라고 쓴 것만으로 이 API를 대신하지 않는다.

API 51은 requests.care_detail을 부분 수정하고 missing_fields를 다시 계산한다. 투약 요청에는 투약 세 칸만, 귀가 요청에는 인계자 세 칸만 허용한다. 등록 인계자는 현재 활성·아이 연결을 다시 검사하고 이름·관계를 갱신한다. UUID를 다른 사람으로 바꾸거나 null로 비우면 이전 사람의 이름·관계를 지우고 이번 입력이나 등록 정보로 채운다. 구조화 입력을 바꾸면 received로 돌아가고 confirmed_at을 지우며 입력 판을 1 올린다. care_updated 이력에는 fields·version만 남기고 값은 care_detail에 둔다. 담당자(없으면 원장)에게 care_requested("보호자가 입력을 수정했어요. 다시 확인해 주세요.")를 보낸다. 미등록 인계자로 바뀌면 checked 이력의 pickup_snapshot과 원장 경고를 바로 남긴다. 같은 이름·관계의 경고 중복 제거는 confirm과 공유한다. 원래 본문·대화는 바꾸지 않고 AI를 부르지 않는다. 수정·취소·반려도 확인·완료와 같은 요청 행 잠금으로 직렬화한다.

CareOut은 version·pickup_guardian_id·pickup_name·pickup_relation·unregistered_pickup, medication_name·medication_dose·medication_time·missing_fields·confirmed_at·completed_at으로 이뤄진다. 다른 요청 유형이면 care는 null이다. 확인·완료 시각은 한국 시각으로 주고, 교직원 신원은 응답에 넣지 않는다. 학부모는 기존 목록·상세·대화·SSE에서도 자기 요청을 볼 수 있다. 이때 SSE는 AI 단계 없이 현재 상태를 담은 done 하나로 끝난다. 민원용 POST /confirm과 상담 시간 선택은 409 INVALID_TRANSITION이다.

알림 종류는 접수·입력 수정 때 담당자에게 가는 care_requested, confirm하면 신청 학부모에게 가는 care_confirmed, 완료하면 학부모에게 가는 completed, 반려하면 학부모에게 가는 care_rejected, 학부모 취소 때 담당자에게 가는 cancelled다. 정정과 미등록 인계자 경고에는 기존 care_requested를 고정 본문과 함께 쓰며, 알림에 투약 지시나 추가 대화 원문은 싣지 않는다. 귀가 알림은 아이 안전 때문에 18시 뒤나 주말에도 즉시 보내고, 발송에 실패해 재시도할 때도 근무일로 미루지 않는다. 반면 투약의 교직원 알림은 기존 근무 시간 규칙을 유지한다. 같은 이벤트·같은 수신자 알림은 한 번만 만든다.

알림장 초안은 같은 날 요청의 원문과 request 출처를 medication·pickup 줄로 연결한다. content.items[].request_status는 읽기 전용이며, 연결된 요청의 현재 상태(received·assigned·completed·rejected)를 보여 준다. 보호자가 정정한 뒤에는 received로 보인다. 이 값은 PATCH에 담아 보내도 저장하지 않고, content·ai_original·발송 시점 본문도 고쳐 쓰지 않는다. 알림장을 확인하거나 발송해도 투약·인계가 완료되지는 않는다. 출처는 같은 아이·같은 유형의 request만 허용하며, 다른 출처는 422다. 목록은 한 연결에서 연결된 요청 상태를 한 번에 읽는다.

오류는 기존 공통 형식을 따른다. 인증이 없으면 401, 학부모가 교직원 기능을 부르면 403 FORBIDDEN_ROLE, 범위 밖이면 404 NOT_FOUND, 단계·유형이 맞지 않으면 409 INVALID_TRANSITION, 옛 입력 판으로 보내면 409 CARD_VERSION_CONFLICT다. 명시한 인계자 UUID가 맞지 않거나 형식이 틀리면 422 VALIDATION_FAILED이고, 이때 details.field는 pickup_guardian_id다. 다만 미등록 인계자와 투약 누락 자체는 422 사유가 아니다.

저장에는 requests·request_messages·events·notifications를 쓴다. 투약·귀가 구조화 입력은 requests.care_detail(jsonb)에 저장하며, 접수 이벤트 detail에는 값 대신 fields(구조화 입력의 칸 이름 목록)와 trace_id만 남긴다. 상세 care와 missing_fields는 care_detail에서 읽고, 보호자 원문을 옮기는 알림장 줄은 기존처럼 requests.body를 쓴다. confirm에는 pickup_snapshot·version·care_decision을, 추가 대화의 message_added에는 care_message·message_id·version을 남긴다. 입력 수정은 care_updated(fields·version), 취소는 cancelled(cancelled_by_parent·version), 반려는 dismissed(care_decision=reject·reason_text·version)다. 시각과 입력 판은 이 순서 있는 이력에서 읽는다. 0012가 care_detail을 추가하고 기존 접수 이력의 입력 값을 이관한다. 알림 종류 care_requested·care_confirmed는 0008에서, 피드·앨범(3.29)의 새 표·칸은 0010에서 더한다.

### 3.28 [제안] 상담 지연 입력

`POST /api/v1/consultations/{booking_id}/delay`는 JWT를 가진 그 반의 예약 담임만 호출할 수 있다. 반 배정 기간과 기관·요청 범위도 함께 확인한다. 학부모·원장이 부르면 403 FORBIDDEN_ROLE이고, 같은 반 교사라도 예약 담임이 아니면 403 FORBIDDEN_ROLE이다. 다른 반·다른 기관의 예약이나 없는 예약은 404 NOT_FOUND다. 예약이 확정 상태이고 요청이 sent_or_booked여야 하며, 그 밖의 상태면 409 INVALID_TRANSITION이다.

본문은 `{ "expected_end_at": "2026-11-16T09:55:00+09:00" }`이고, 시각에는 오프셋을 포함해야 한다. 지연은 상담이 시작된 뒤에만 기록할 수 있다. 예상 종료는 현재·원래 종료보다 뒤여야 하고, 원래 종료 + 3시간 이내이면서 예약 시작과 같은 한국 날짜여야 한다. 하나라도 틀리면 422 VALIDATION_FAILED다. UTC로 보내도 받으며, 응답은 한국 시각으로 맞춰 돌려준다.

422 VALIDATION_FAILED가 나는 조건은 아래 다섯 가지다(`app/core/consultation_alerts.py`의 `valid_delay`). 응답에는 어느 조건이 틀렸는지 따로 적지 않는다.

| # | 조건 | 틀리는 흔한 경우 |
| --- | --- | --- |
| 1 | `expected_end_at`에 시간대(오프셋)가 있다 | `2026-11-16T09:55:00`처럼 `+09:00`·`Z`를 빼고 보냄 |
| 2 | 상담이 이미 시작됐다(지금 ≥ 예약 시작) | 시작 전에 누름. 화면은 시작 전 버튼을 잠근다 |
| 3 | 예상 종료가 원래 종료보다, 그리고 지금보다 뒤다 | 이미 지난 시각, 원래 종료와 같거나 앞선 시각 |
| 4 | 예상 종료가 원래 종료 + 3시간 이내다 | 원래 종료에서 3시간 넘게 늦춤. 끝난 지 3시간이 지난 예약은 3번과 함께 만족하는 시각이 없음 |
| 5 | 예상 종료가 예약 시작과 같은 한국 날짜다 | 늦은 시각 예약에서 자정을 넘김 |

시험용으로 과거 날짜 예약을 만들면 2번은 통과하지만, 지금 시각이 원래 종료 + 3시간을 넘기면 3·4번을 함께 만족할 수 없어 항상 422가 난다. 성공 응답을 확인하려면 지금 진행 중인 상담(시작 ≤ 지금 < 종료 + 3시간)을 쓴다.

성공하면 200을 돌려준다.

```json
{"booking":{"id":"00000000-0000-4000-8000-000000000901",
 "period":{"start":"2026-11-16T09:00:00+09:00","end":"2026-11-16T09:30:00+09:00"},
 "status":"confirmed","expected_end_at":"2026-11-16T09:55:00+09:00"},"affected_bookings":1}
```

`affected_bookings`는 뒤에 이어지는 확정 예약 가운데 같은 기관에서 담임이나 상담실을 함께 쓰고, 새 예상 종료와 시작이 겹치는 예약의 수다. 사람 수나 알림 수가 아니다. 같은 시각을 다시 보내면 지연 이력도, 같은 시각의 알림도 늘리지 않는다. 예약의 period와 확정 상태는 바꾸지 않는다. 저장한 뒤에는 그 예약 담임의 같은 한국 날짜 예약만 한 번 점검한다. 그래서 mock에서도 이 API → 알림 목록 순서로 지연 시 대체 시간 제안을 재현할 수 있다. DB에서는 Beat도 점검한다. 점검이 잠겨 있으면 다음 Beat가 처리하므로, 응답의 수가 발송 완료를 뜻하지는 않는다.

대체 시간은 안내일 뿐 미리 잡아 두지 않는다. **예약 변경·취소로 대체 시간을 받아들이는 경로와 실제 상담 종료 입력·화면 연결은 후속 계약**으로 정하며, 이 절에서는 만들지 않는다.



### 3.29 [제안] 피드·앨범

API 38~49는 2장 표의 경로를 쓰며 모두 `/api/v1` 아래에 있다. 사진 AI(T50)가 붙기 전에는 올린 사람이 아이를 직접 표시한다. 올린 사람이 아이 표시를 빠뜨리면 그 사진은 칸 규칙만 따르게 되므로, 화면에서 아이를 표시하도록 안내해야 한다.

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 보호자끼리 반 칸에서 글을 나누고, 같은 기관 구성원이 원 칸 글·사진을 본다(FR-22·AC-06) |
| ② 요청 헤더 | JWT 필수. 생성은 multipart/form-data, 숨김·범위 변경은 application/json이다 |
| ③ 경로·쿼리 | 기관·반·글·사진·아이 ID는 UUID다. 목록은 기존 규칙대로 page=1·size=20(최대 100)·sort=-created_at이고, 오름차순은 created_at이다. 동률이면 같은 방향의 id로 정렬한다. 앨범의 child_id로는 보호자가 자기 아이만 고를 수 있다 |
| ④ 요청 본문 | 글 생성은 body 1~2,000자(공백만으로는 안 됨), files 0~10장이다. child_ids는 파일 순서대로 아이 UUID 배열을 담은 JSON 문자열이다. 예: [["아이 UUID"],[]]. 기본 []는 모든 사진에 태그가 없다는 뜻이다. 숨김은 {"status":"hidden"}, 범위 변경은 {"photo_scope":"family"}(family·class·org 중 하나)다 |
| ⑤ 검증·권한 | 칸 권한을 먼저 검사하고, 그다음 사진 공개 범위를 검사한다. class 칸은 그 반 아이의 보호자만 읽고 쓴다. 교직원이나 다른 반 보호자가 접근하면 목록·상세·앨범·파일 모두 403 FORBIDDEN을 돌려주고 permission_denied 이력을 남긴다. org 칸은 같은 기관의 교직원과, 지금 연결된 아이(`child_guardians`)가 하나라도 있는 보호자가 읽고 쓴다. 연결된 아이가 없는 보호자(퇴소 등)가 접근하면 목록·상세·앨범·파일·글 올리기 모두 403 FORBIDDEN을 돌려주고 permission_denied 이력을 남긴다. 다른 기관이나 없는 자원은 404다. 다른 아이의 범위를 조회·변경하거나, 남의 글을 삭제하거나, 원장이 아닌 사람이 숨기려 해도 403이다 |
| ⑥ 정상 응답 | 글 생성 201과 상세/숨김 200은 {post: Post}, 목록·앨범은 {items,total,page,size}다. 범위 조회·변경 200은 {child_id,photo_scope}, 삭제는 204다. 파일은 검사한 형식의 바이트를 Cache-Control: private, no-store·X-Content-Type-Options: nosniff·Content-Disposition: inline과 함께 준다 |
| ⑦ 오류 응답 | 공통 형식으로 401 UNAUTHENTICATED, 403 FORBIDDEN, 404 NOT_FOUND, 422 VALIDATION_FAILED를 준다. 태그한 아이가 다른 반/원 아이이거나, 태그가 중복되거나, 배열 수가 맞지 않아도 422다. 업로드 몸통이 51MiB를 넘으면 413 VALIDATION_FAILED다 |
| ⑧ 저장·이력 | feed_posts·feed_photos·feed_photo_children, children.photo_scope(0010)를 쓴다. 생성·삭제·숨김·범위 변경은 events에 feed_post_created·feed_post_deleted·feed_post_hidden·photo_scope_changed로 남기며 trace_id·대상 ID를 함께 적는다. 새 알림은 만들지 않는다 |

Post는 id·lane(class/org)·classroom_id(org 칸은 null)·author_id·body·status(published/hidden)·created_at·photos를 준다. Photo는 id·post_id·media_type·size_bytes·created_at·file_url만 주고, 저장 경로·sha256·태그·숨은 사진 개수는 주지 않는다. file_url은 `/api/v1/photos/{photo_id}/file`이며 공개 정적 주소는 없다.

아이별 photo_scope 기본값은 family다. family는 그 아이의 보호자와 올린 사람, class는 반 칸까지, org는 반·원 칸까지 허용한다. 보호자가 여럿이면 마지막 변경을 따른다. 사진을 보여 줄지는 칸 권한을 통과한 뒤에 정한다. 올린 사람은 모든 사진을 본다. 다른 사람은 표시된 아이 **전원**에 대해, 그 아이가 자기 아이이거나 그 아이의 공개 범위가 이 칸을 덮어야 볼 수 있다. 태그가 없는 사진은 칸 권한만 본다. 볼 수 없는 사진은 글의 photos와 앨범에서 빼고 앨범 total에도 세지 않으며, 파일은 404다. 관계와 공개 범위는 매번 현재 값을 읽으므로, 바꾸면 지난 사진에도 바로 적용된다.

사진은 가상 자료만 쓴다. 형식은 확장자나 전송 MIME이 아니라 첫 바이트로 jpeg·png·webp인지 검사하고, 장당 5MiB(5,242,880바이트)까지 받는다. 칸 권한은 몸통을 읽기 전에 검사한다. Content-Length와 읽는 동안 쌓인 크기는 10장×5MiB + 1MiB(51MiB)까지 허용하고, 파일이 10개를 넘거나 일반 필드가 2개를 넘으면 422다. 파일은 MEDIA_DIR에 UUID 이름으로 저장하고, DB에는 경로·형식·크기·sha256만 둔다. 생성에 실패하면 이미 저장한 파일도 정리한다. mock은 MEDIA_DIR/mock 아래를 쓰며, 초기화할 때 그 폴더만 비우고 DB 파일은 그대로 둔다.

원장은 원 칸 글만 hidden으로 숨길 수 있다. 숨긴 글·사진은 모든 일반 조회와 파일에서 404이고 목록에서도 빠진다. 같은 기관 작성자는 반 이동이나 퇴소로 칸 권한을 잃어도 숨긴 글까지 삭제할 수 있다. 삭제할 때는 deleted_at과 이력을 먼저 커밋한 뒤 사진 파일을 디스크에서 지운다. 커밋에 실패하면 글·사진·파일을 보존한다. 데모에서는 두 모드가 같은 UUID로 반 글 2개, 원 글 2개, 가상 아이 JPEG 5장을 쓴다.

### 3.30 [제안] 보낸 알림장 정정 — `POST /api/v1/daily-notes/{note_id}/correct`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임·원장이 이미 보낸 알림장의 잘못된 내용을 고치고, 연결된 학부모에게 정정 알림을 남긴다. |
| ② 요청 헤더 | Authorization 필수, X-Request-ID 권장, Content-Type: application/json. |
| ③ 경로·쿼리 | note_id(UUID, 필수). 쿼리는 없다. |
| ④ 요청 본문 | content·reason_text·version 모두 필수. content는 3.7·3.21과 같은 전체 줄 객체다. |
| ⑤ 검증·권한 | teacher는 현재 담당 반만, director는 같은 기관만 허용한다. parent는 403이다. sent만 정정하며 다른 상태는 409 INVALID_TRANSITION, 판이 다르면 409 CARD_VERSION_CONFLICT와 details.current_version을 준다. 요청·문서 출처는 3.21의 범위·아이·공개 범위 검사를 그대로 적용한다. |
| ⑥ 정상 응답 | 200 + {note: NoteView}. 내용 전체를 교체하고 corrected_at을 현재 시각으로 기록하며 version을 1 올린다. 학부모 목록도 같은 content·version·corrected_at을 준다. |
| ⑦ 오류 응답 | 401 UNAUTHENTICATED, 403 FORBIDDEN_ROLE, 404 NOT_FOUND(다른 기관·다른 반·없음), 409 INVALID_TRANSITION 또는 CARD_VERSION_CONFLICT, 422 VALIDATION_FAILED(필수 칸·이유 길이·출처). |
| ⑧ 실행 규칙 | 반 입력→아이 알림장 순서로 잠그고 판을 검사한다. 같은 판의 경합·재전송은 하나만 성공한다. 내용·시각·판·daily_note_corrected 이력·학부모 note_corrected 알림을 한 트랜잭션에서 저장한다. status=sent, sent_at·confirmed_by·confirmed_at·ai_original·open_checks는 유지한다. |

| 필드 | 위치 | 타입 | 필수 | 빈값 | 제약 | 설명 |
| --- | --- | --- | --- | --- | --- | --- |
| note_id | 경로 | UUID | 필수 | 불가 | 담당 반 또는 같은 기관의 sent 알림장 | 정정 대상 |
| version | 본문 | integer | 필수 | 불가 | 1 이상, 조회한 현재 판 | 판 충돌은 409 |
| content | 본문 | object | 필수 | null 불가 | items[]의 key·label·value·source는 3.21과 같음. 빈 items 허용 | 내용 전체 교체 |
| reason_text | 본문 | string | 필수 | 공백만 불가 | 1~500자 | 정정 사유. 교직원 이력에만 저장 |
| note.version | 응답 | integer | 항상 | 불가 | 정정 전 판 +1 | 다음 정정에 사용 |
| note.corrected_at | 응답 | datetime | 항상 | 정정 뒤 값 있음 | 마지막 정정 시각 | 학부모 응답에도 포함 |

```http
POST /api/v1/daily-notes/{note_id}/correct
{"version":1,"content":{"items":[{"key":"day","label":"오늘 하루","value":"산책 대신 실내 놀이를 했어요.","source":{"type":"teacher_input"}}]},"reason_text":"활동 기록 오기 정정"}
HTTP/1.1 200 OK
{"note":{"id":"알림장 UUID","status":"sent","version":2,"corrected_at":"2026-11-24T14:00:00+09:00","content":{"items":[{"key":"day","label":"오늘 하루","value":"산책 대신 실내 놀이를 했어요.","source":{"type":"teacher_input"}}]}}}
```

위 응답은 정정 관련 칸을 발췌했다. 전체는 3.20 NoteView다. version은 정정용 판이며 기존·새 알림장 모두 1로 시작한다. 발송 전 PATCH·확인·재생성·발송은 이 판을 바꾸지 않는다. 정정 이력은 daily_note_id·행위자·sent→sent·detail.reason_text·detail.version·trace_id로 남기고 본문·AI 원본을 이력에 복사하지 않는다. 활성 parent 계정인 현재 보호자마다 알림 한 건을 만들며, 제목은 "알림장이 고쳐졌어요", kind=note_corrected, subject_type=daily_note·subject_id=알림장 ID다. 알림 body에는 정정 이유나 본문을 넣지 않는다. 중복 키는 알림장·정정 판·수신자이며, 새 판으로 다시 정정하면 새 알림을 만든다. 노출·발송 시각은 기존 학부모 deliver_after 규칙을 따른다.

0015_daily_note_correction(down_revision=0014)는 daily_notes.version·corrected_at만 추가한다. daily_note_corrected와 note_corrected는 0012에서 허용한 값을 재사용한다. 두 모드가 같은 계약을 제공한다. 웹 정정 입력·정정 시각 표시는 웹 담당 범위다.

### 3.31 [제안] 필수 동의 — 내 동의 저장·조회와 반 현황

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 로그인한 사람이 역할별 필수 항목에 전부 동의하고, 원장·담임은 아이별 보호자의 완료 현황을 확인한다(API 53~55). |
| ② 요청 헤더 | Authorization 필수, X-Request-ID 권장. POST는 Content-Type: application/json. |
| ③ 경로·쿼리 | GET·POST `/api/v1/consents`는 경로·쿼리가 없다. GET `/api/v1/classrooms/{classroom_id}/consents`는 반 UUID를 받는다. |
| ④ 요청 본문 | POST만 `{"items":["terms","privacy","ai_processing"],"terms_version":"2026-11-26"}`. 교사·원장 예시이며 보호자는 아래 세 항목도 전부 보낸다. |
| ⑤ 검증·권한 | 내 동의는 로그인한 사람만 저장·조회한다. 반 현황은 같은 원의 원장·현재 그 반 담임만 조회하며 다른 반 담임·학부모는 403, 없는 반·다른 원은 404다. |
| ⑥ 정상 응답 | 내 동의는 200 `{terms_version,complete,items:[{item,label,required:true,agreed_at}]}`. 반 현황은 200 `{items:[{child_id,display_name,guardians_total,guardians_complete,complete}]}`. |
| ⑦ 오류 응답 | 401 UNAUTHENTICATED. 필수 항목 누락은 422 CONSENT_INCOMPLETE(`details.missing_items`), 다른 역할 항목·모르는 항목·허용되지 않은 본문 키는 422 VALIDATION_FAILED, 판 불일치는 409 CONSENT_VERSION_MISMATCH(`details.terms_version`은 현재 판). |
| ⑧ 실행 규칙 | 현재 판은 코드 상수 CONSENT_VERSION="2026-11-26" 하나로 둔다. 같은 요청은 최초 agreed_at·응답을 유지하고 이력도 중복하지 않는다. 새 기록을 넣었을 때만 consent_agreed 한 줄을 함께 남긴다. 이전 판 기록은 보존한다. |

| 항목 키 | 표시 문구 | 적용 역할 | required |
| --- | --- | --- | --- |
| terms | 이용약관 | 보호자·교사·원장 | true |
| privacy | 개인정보 수집·이용 | 보호자·교사·원장 | true |
| ai_processing | 쓴 글이 AI 처리를 위해 국외 AI 사업자(OpenAI, 미국)에게 전송되고, 처리 기록은 점검을 위해 LangSmith(미국)에 14일 보관됨 | 보호자·교사·원장 | true |
| child_info | 자녀 개인정보 | 보호자 | true |
| child_health | 자녀 건강·투약 정보 | 보호자 | true |
| child_face | 자녀 얼굴로 찾기 | 보호자 | true |

GET은 내 역할의 항목만 돌려준다. 현재 판에 기록이 없으면 agreed_at=null이며, 항목이 전부 채워졌을 때만 complete=true다. POST는 역할별 필수 항목을 전부 받아 한 번에 저장한다. 일부 항목만 저장하거나 항목별로 철회하는 API는 두지 않는다. 아직 가입 API와 얼굴 특징정보 저장이 없으므로 로그인한 사용자 동의만 다룬다. 탈퇴·데이터 삭제는 이번 범위 밖이다.

반 현황의 guardians_total은 아이에게 연결된 보호자 수이고, guardians_complete는 그중 현재 판의 보호자 필수 항목을 모두 동의한 수다. 한 명 이상 완료하면 아이의 complete=true다. 보호자가 없으면 두 수는 0, complete=false다. 반환 순서는 아이 이름·ID 순이다.

**미동의 차단.** 기존 역할·기관·반·아이 권한 검사 뒤, 업무 처리 전 공용 require_complete로 현재 판을 확인한다. 미완료면 403 CONSENT_REQUIRED다. 아래 일곱 경로(쓰기 여섯과 교직원 AI 질문)와, 같은 요청 생성 함수를 쓰는 알림장 답장(3.34)에 적용하며 GET과 나머지 동작은 기존대로 제공한다. 피드 업로드는 권한·동의를 검사한 뒤 multipart 몸통을 읽는다.

- POST `/api/v1/requests`
- POST `/api/v1/requests/{request_id}/messages`
- POST `/api/v1/daily-notes/drafts`
- POST `/api/v1/daily-notes/drafts/{input_id}/regenerate`
- POST `/api/v1/classrooms/{classroom_id}/posts`
- POST `/api/v1/organizations/{org_id}/posts`
- POST `/api/v1/staff/ask` (질문을 AI에 보내므로)

GET `/api/v1/me`와 로그인 응답의 user.consents_complete도 같은 판·역할 기준이다. 데모 시드는 mock·DB 모든 시드 계정을 현재 판으로 완료시켜 기존 시연을 유지한다. 0016은 동의 행을 넣지 않고 표·이력 허용 값만 만든다. 실제 동의 화면은 후속이며 호출 순서는 백엔드 구현 기록에 적었다.

### 3.32 [제안] 바쁜 시간 — 본인 일정 관리와 원장 조회

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 수업·회의·당번 등 상담을 잡을 수 없는 시간을 관리한다(API 59~61). |
| ② 요청 헤더 | Authorization 필수, X-Request-ID 권장. POST는 Content-Type: application/json. |
| ③ 경로·쿼리 | GET `/api/v1/staff/busy-blocks?from=2030-01-07T09:00:00%2B09:00&to=2030-01-08T00:00:00%2B09:00`. from·to는 필수이며 시간대가 있는 시각, from < to다. 원장만 user_id(UUID)로 같은 기관 교직원을 조회할 수 있다. DELETE는 정수 id다. |
| ④ 요청 본문 | POST `{"start_at":"2030-01-07T09:30:00+09:00","end_at":"2030-01-07T12:00:00+09:00","kind":"class"}`. 시간대 필수, start_at < end_at, kind는 class·meeting·duty·off·other만 허용한다. 다른 키는 받지 않는다. |
| ⑤ 검증·권한 | 교사·원장만 호출한다(보호자는 403). POST·DELETE는 본인 일정만 관리하며 원장도 남의 일정은 지우지 못한다. 다른 교직원 조회·삭제, 다른 기관·없는 대상은 404 NOT_FOUND로 거부하고 호출자 기관의 permission_denied 이력을 남긴다. |
| ⑥ 정상 응답 | GET 200 `{items:[{id,user_id,start_at,end_at,kind}]}`, 시작 시각·id 오름차순. POST 201 `{id,user_id,start_at,end_at,kind}`. DELETE 204, 본문 없음. |
| ⑦ 오류 응답 | 401 UNAUTHENTICATED, 403 FORBIDDEN_ROLE, 404 NOT_FOUND, 형식·순서 오류 422 VALIDATION_FAILED, 확정 상담과 겹치는 등록은 409 SLOT_TAKEN. |
| ⑧ 실행 규칙 | 조회·겹침은 반개구간 [시작,끝) 기준이다. 확정(confirmed) 상담은 지연 보고 expected_end_at까지 막고, cancelled·done은 막지 않는다. 등록과 상담 확정이 같은 담임 잠금을 사용하며 이전 후보도 확정 직전에 바쁜 시간을 재검사한다. 수정 API는 없으며 삭제 후 다시 등록한다. |

기존 staff_busy_blocks 표를 사용하며 새 마이그레이션은 없다. 가상 teacher01·02에게 시드 기준일부터 14일 동안 평일마다 09:30~12:00(class), 13:00~14:00(duty)를 채운다. DB 재실행은 같은 기간·종류를 중복하지 않고 확정 상담과 겹치는 시드는 건너뛴다. 기존 고정 날짜 평가 픽스처는 보존한다. 상담 후보 계산은 이 시간을 제외한다.

### 3.33 [제안] 하루 중 기록 — 아이별 관찰과 알림장 메모

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 담임이 관찰을 짧게 쌓고, 알림장 초안(API 22)에 아이별 메모로 쓴다(API 56~58). |
| ② 요청 헤더 | Authorization 필수, X-Request-ID 권장. POST는 Content-Type: application/json. |
| ③ 경로·쿼리 | GET `/api/v1/classrooms/{classroom_id}/records?date=2026-11-26`. 반은 UUID, date는 필수 YYYY-MM-DD다. POST도 같은 반 경로, DELETE `/api/v1/records/{record_id}`는 기록 UUID다. |
| ④ 요청 본문 | POST `{"child_id":"00000000-0000-4000-8000-000000000501","body":"블록을 나누어 쌓았어요.","note_date":"2026-11-26"}`. body는 1~500자, note_date 생략 시 KST 오늘이다. 다른 키는 받지 않는다. |
| ⑤ 검증·권한 | 읽기·등록은 현재 그 반 담임, 같은 기관 원장은 읽기만 한다. 삭제는 같은 기관 작성 교사 또는 현재 그 반 담임만 한다. 보호자는 403, 원장의 쓰기도 403이다. 다른 기관·반·아이, 없는 대상은 404로 거부하고 permission_denied를 남긴다. 아이는 지정 반에 속해야 한다. |
| ⑥ 정상 응답 | GET 200 `{items:[{id,classroom_id,child_id,note_date,body,author_id,created_at}]}`, child_id·created_at·id 오름차순이다. POST 201은 같은 기록 객체, DELETE 204는 본문이 없다. |
| ⑦ 오류 응답 | 401 UNAUTHENTICATED, 403 FORBIDDEN_ROLE, 404 NOT_FOUND, UUID·날짜·글 길이·허용되지 않은 본문 키는 422 VALIDATION_FAILED. |
| ⑧ 실행 규칙 | 삭제는 deleted_at만 채우며 다시 삭제하면 404다. 조회와 초안 입력에서 삭제 기록을 뺀다. 초안 만들기·다시 만들기는 같은 원·반·날짜의 기록을 아이별 시간순으로 줄바꿈해 합친다. child_memos에 명시한 아이는 그 메모가 우선이며 공백 메모도 서버 기록으로 대체하지 않는다. API 22의 요청·응답 칸은 그대로다. |

0018 표·활성 기록 부분 인덱스를 사용한다. 데모 적재 시 별빛반 아이마다 최초 적재일의 오늘·어제 가상 관찰 두 줄을 넣고 재실행 때 날짜·삭제 표시를 보존한다.

### 3.34 [제안] 알림장 답장·준비물 '챙겼어요'

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 발송된 알림장의 답장을 새 문의로 접수하고(API 62), 준비물을 챙겼음을 표시한다(API 68). 별도 답장 표는 만들지 않는다. |
| ② 요청 헤더 | Authorization 필수, X-Request-ID 권장. 답장은 Content-Type: application/json. |
| ③ 경로 | POST `/api/v1/daily-notes/{note_id}/replies`, POST `/api/v1/daily-notes/{note_id}/supplies-check`. note_id는 UUID다. |
| ④ 요청 본문 | 답장 `{"body":"내일 준비물은 무엇인가요?"}`. 기존 문의와 같은 1~2000자 문자열이다. 준비물 확인은 본문이 없다. |
| ⑤ 검증·권한 | 해당 아이의 현재 보호자만 호출한다. 교직원은 403 FORBIDDEN_ROLE. 다른 아이·기관·없는 알림장·발송 전 알림장은 404 NOT_FOUND로 숨기고 permission_denied 이력을 남긴다. 준비물 줄(key=supplies)이 없거나 값이 빈 문자열·공백뿐이면 409 INVALID_TRANSITION이다. 답장은 기존 문의 생성의 필수 동의 검사도 적용한다. |
| ⑥ 정상 응답 | 답장 202 `{"request_id":"00000000-0000-0000-0000-000000000901"}`. 준비물 확인 200 `{"supplies_checked_at":"2026-11-26T18:00:00+09:00"}`. 다시 누르거나 동시에 눌러도 첫 확인 시각을 돌려준다. |
| ⑦ 오류 응답 | 401 UNAUTHENTICATED, 403 FORBIDDEN_ROLE·CONSENT_REQUIRED, 404 NOT_FOUND, 409 INVALID_TRANSITION, 422 VALIDATION_FAILED. |
| ⑧ 실행 규칙 | 답장은 API 3의 요청 생성 함수를 그대로 호출하여 type=inquiry·source_note_id를 함께 저장한다. 이후 분류·근거 검색·담임 카드·알림·사람 승인은 기존 문의 흐름을 따른다. 호출마다 새 요청이며 별도 분류 로직은 없다. |

응답은 기존 칸을 유지하고 다음 칸만 더한다.

| 응답 위치 | 추가 칸 | 의미 |
| --- | --- | --- |
| 요청 상세 `request`·카드 상세 `request` | `source_note: {note_id, note_date} \| null` | 답장 원문의 ID·날짜. 일반 요청은 null이다. |
| GET `/api/v1/daily-notes`의 `items[]` | `replies: [{request_id, body, status, created_at}]` | 해당 알림장에서 접수한 문의를 생성 시각·ID 오름차순으로 표시한다. 없으면 빈 배열이다. status는 요청의 현재 상태이며 승인 뒤에도 갱신된다. |
| GET `/api/v1/daily-notes`의 `items[]` | `supplies_checked_at: datetime \| null` | 최초 준비물 확인 시각. 학부모·담임·원장 모두 같은 값을 본다. 확인 전에는 null이다. |

알림장 수정·정정의 `note` 응답에도 같은 추가 칸을 제공한다. 확인은 알림장의 content·상태·정정 version·sent_at을 바꾸지 않는다. 저장은 0019의 `requests.source_note_id`(기관 짝 FK)·`daily_notes.supplies_checked_at` 두 칸을 쓴다.

### 3.35 [제안] 원 일정 — `GET /api/v1/calendar`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 사용 중인 일정표·가정통신문에서 조회 기간과 하루라도 겹치는 날짜 사실을 읽는다(API 63). |
| ② 요청 헤더 | Authorization 필수, X-Request-ID 권장. |
| ③ 경로·쿼리 | 경로 변수 없음. from·to 둘 다 필수이며 기존 날짜 쿼리처럼 YYYY-MM-DD로 보낸다. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | 자기 기관만 조회한다. 원장은 기관 전체, 담임은 현재 담당 반, 학부모는 현재 연결된 아이의 반 자료를 본다. 대상 반이 없는 기관 전체 자료는 모두 볼 수 있다. 학부모에게 staff 자료는 제외한다. 목록에서 반·공개 범위 밖 자료는 조용히 제외하고 permission_denied 이력을 만들지 않는다. 다른 기관 자료는 읽지 않는다. |
| ⑥ 정상 응답 | 200 `{items:[{date,end_date,title,document_id,document_title,location,sources:[{document_id,document_title,location}],conflict,conflict_dates}]}`. 없으면 items=[]. |
| ⑦ 오류 응답 | 로그인 없음·무효는 401 UNAUTHENTICATED. 날짜 생략·잘못된 날짜·from>to는 422 VALIDATION_FAILED. 공통 오류 형식은 1.4와 같다. |
| ⑧ 실행 규칙 | status=active·ingest_status=succeeded인 schedule·notice만 대상으로 기존 extract_facts를 재사용한다. 날짜 사실만 쓰며 AI·임베딩은 호출하지 않는다. 자료의 시행 전 일정도 조회할 수 있다. |

| 방향 | 칸 | 형식·의미 |
| --- | --- | --- |
| 입력(query) | from, to | 필수 date. 양 끝을 포함하는 조회 구간. |
| 출력 | items[].date | date. 단일 날짜 또는 기간의 시작일. |
| 출력 | items[].end_date | date 또는 null. 기간의 종료일이며 단일 날짜는 null. |
| 출력 | items[].title | string. extract_facts가 정규화한 일정 이름. |
| 출력 | items[].document_id, document_title | UUID string·string. 일정의 원 자료 ID와 제목. |
| 출력 | items[].location | string. extract_facts의 근거 위치 그대로. 위치가 없는 조각은 빈 문자열. |
| 출력 | items[].sources[] | array. 같은 일정을 적은 자료 전부 `{document_id,document_title,location}`. 첫 항목이 위 document_id·document_title·location과 같다. |
| 출력 | items[].conflict | boolean. 조회 구간 안에서 같은 이름의 일정이 자료마다 다른 날에 시작하면 true. |
| 출력 | items[].conflict_dates | date array. conflict가 true일 때 그 이름의 시작일들(오름차순). 아니면 빈 배열. |

기간과 조회 구간이 하루라도 겹치면 원래 시작·종료일을 유지해 반환한다. 예를 들어 12/28 하루 조회에도 12/24~1/3 방학을 포함한다. date·title·document_title·location 오름차순이다. 시작일·종료일이 같고 이름이 띄어쓰기만 다른 일정은 한 항목으로 합치고, 기존 칸은 이 순서의 첫 자료로 채우며 모든 자료를 sources에 담는다. 자료마다 겨울방학이 12/24·12/26으로 다르면 어느 쪽이 맞는지 알 수 없으므로 각각 반환하고, 두 항목 모두 conflict=true·conflict_dates=[12/24, 12/26]으로 표시한다. 한 날짜를 선택하지 않는다. 새 DB 표·마이그레이션은 없다.

```json
{"items":[{"date":"2026-12-24","end_date":"2027-01-03","title":"겨울방학","document_id":"00000000-0000-4000-8000-000000000b02","document_title":"[가상] 겨울방학 안내","location":"1쪽 겨울방학 기간","sources":[{"document_id":"00000000-0000-4000-8000-000000000b02","document_title":"[가상] 겨울방학 안내","location":"1쪽 겨울방학 기간"}],"conflict":true,"conflict_dates":["2026-12-24","2026-12-26"]}]}
```

### 3.36 [제안] 개인 알림 시간 — API 64·65

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 교직원이 본인 알림을 받지 않을 시간을 조회·변경한다. |
| ② 요청 헤더 | Authorization 필수, X-Request-ID 권장. PATCH는 Content-Type: application/json. |
| ③ 경로·쿼리 | GET·PATCH `/api/v1/me/notification-settings`. 경로 변수·쿼리는 없다. |
| ④ 요청 본문 | PATCH는 `{"quiet_start":"22:00","quiet_end":"07:00"}`. 두 칸 모두 필수다. |
| ⑤ 검증·권한 | 담임·원장 본인만 사용한다. 사용자·기관 ID를 입력받지 않는다. 학부모는 403 FORBIDDEN_ROLE. |
| ⑥ 정상 응답 | 모두 200, 요청과 같은 두 칸. 설정이 없거나 둘 다 null로 해제하면 두 칸 모두 null. |
| ⑦ 오류 응답 | 로그인 없으면 401 UNAUTHENTICATED. 누락·형식 오류·하나만 null·같은 시각·추가 키는 422 VALIDATION_FAILED. |
| ⑧ 실행 규칙 | KST의 시작 이상·끝 미만을 피한다. 자정을 넘을 수 있다. 둘 다 null이면 행을 지워 기본 WORK_HOURS·근무일 규칙으로 돌아간다. |

| 칸 | 방향 | 타입 | 필수·허용값 | 의미 |
| --- | --- | --- | --- | --- |
| `quiet_start` | PATCH 입력·GET/PATCH 출력 | string 또는 null | 두 칸 모두 필수, HH:MM(00:00~23:59) 또는 둘 다 null | 조용한 시간 시작 |
| `quiet_end` | PATCH 입력·GET/PATCH 출력 | string 또는 null | 시작과 다른 HH:MM 또는 둘 다 null | 조용한 시간 종료 |

응답 예: `{"quiet_start":"22:00","quiet_end":"07:00"}`. 개인 설정은 하루 중 시간대만 WORK_HOURS 대신 바꾸며 주말·HOLIDAYS의 보류는 유지한다. 근무일이면 조용한 시간 밖은 바로, 안이면 quiet_end로 미루고, 그 결과가 근무일이 아니면 다음 근무일의 quiet_end로 미룬다. 예를 들어 토요일 12시와 금요일 23시는 모두 월요일 07시로 미룬다(월요일이 공휴일이면 다음 근무일 07시). 개인 설정은 알림 생성·발송·재시도 때 수신자 기준으로 읽으며 학부모·귀가·설정된 긴급 위험 종류의 즉시 알림은 그대로다.


### 3.37 [제안] 교직원 AI에게 묻기 — `POST /api/v1/staff/ask`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 교직원이 원 자료를 근거로 질문에 답을 받는다(API 66, Y-130). |
| ② 요청 헤더 | Authorization 필수, Content-Type: application/json, X-Request-ID 권장. |
| ③ 경로·쿼리 | 경로 변수·쿼리 없음. 기관·반은 현재 로그인과 담당 관계로 판별한다. |
| ④ 요청 본문 | `{"question":"준비물은 무엇인가요?"}`. 기존 요청 본문처럼 최대 2,000자이며 앞뒤 공백을 뺀 뒤 빈 질문과 추가 키는 거부한다. |
| ⑤ 검증·권한 | 담임·원장만. 담임은 같은 기관의 원 전체 자료와 현재 담당 반 자료, 원장은 같은 기관 전체 자료. 범위 밖 자료는 검색에서 제외한다. |
| ⑥ 정상 응답 | 200 `{answer,evidence:[{document_id,title,location,effective_date}],conflict}`. 검증된 인용만 출처로 돌려준다. |
| ⑦ 오류 응답 | 401 UNAUTHENTICATED, 학부모 403 FORBIDDEN_ROLE, 현재 판 필수 동의 전 403 CONSENT_REQUIRED(모델을 부르지 않음, 3.31), 질문 형식 오류 422 VALIDATION_FAILED, 모델 호출 실패 503 UPSTREAM_UNAVAILABLE. 공통 오류 형식(1.4) 유지. |
| ⑧ 실행 규칙 | 기존 search_documents와 문의 답변 흐름(인용 확인·검사·재작성)을 재사용한다. notice·schedule·menu·policy의 active·적재 성공·기간 미종료 자료만 검색하며 시행 전 안내도 포함한다. 요청·카드·알림을 만들지 않고 events에 tool_called·agent_name=document·호출자·trace_id·근거 수만 남긴다. 모델 실패도 tool_failed·code=UPSTREAM_UNAVAILABLE 이력을 남긴다. 질문·답변 원문과 예외 원문은 이력에 저장하지 않는다. |

| 필드 | 위치 | 타입 | 필수·빈값 | 설명 |
| --- | --- | --- | --- | --- |
| question | 입력 본문 | string | 필수, 공백만 불가 | 앞뒤 공백 제거 후 1~2,000자 |
| answer | 응답 | string | 200에서 항상 | 검증된 답변. 근거 없음·인용 검증 실패는 `자료에서 못 찾았어요` |
| evidence | 응답 | object[] | 항상, 빈 배열 가능 | 답변에서 인용 검증을 통과한 자료 조각 순서 |
| conflict | 응답 | boolean | 항상 | 평소 false, 답변 흐름이 자료 충돌을 판별하면 true |
| evidence[].document_id·title·location | 응답 | UUID·string·string | 항상 | 문서 ID·제목·원문 위치. 위치가 없으면 본문 |
| evidence[].effective_date | 응답 | date 또는 null | 항상, null 가능 | 문서 effective_from |

- 자료 충돌: 200, answer=`자료마다 내용이 달라요. 아래 두 자료를 확인해 주세요.`, conflict=true, 충돌한 양쪽 자료의 검증된 evidence를 반환한다(겨울방학 12/24·12/26 둘 다). 검색·인용에 없는 출처는 만들지 않는다.
- 모델 호출 실패: 기존 답변 흐름의 모양 오류·검사 재시도를 유지하며, 재시도 뒤에도 모델 오류로 답변을 못 만들면 503 `UPSTREAM_UNAVAILABLE`, 1.4의 `{error:{code,message,trace_id,details}}` 형식을 반환한다. 재시도에 성공하면 정상 200이다. ModelError 이외의 예외도 503이다.
- 근거 없음: 200, answer=`자료에서 못 찾았어요`, evidence=[], conflict=false. 인용·검사 검증에서 근거를 확정하지 못해도 같은 안전 응답을 쓴다.

모델에 보내는 질문·자료 제목·위치·본문·검사 입력은 기존 mask_sensitive를 통과한다. 지시문이 섞인 조각은 기존 guardrails로 제외한다. 근거가 없으면 모델을 호출하지 않는다. mock·DB 계약은 같으며 시험에는 가짜 작성·검사 모델을 주입한다. 새 표·마이그레이션은 없다.

```json
{"answer":"준비물은 수건이에요.","evidence":[{"document_id":"00000000-0000-4000-8000-000000000066","title":"가상 준비 안내","location":"1쪽 준비물","effective_date":"2026-12-01"}],"conflict":false}
```

### 3.38 [제안] 재배정할 선생님 목록 — `GET /api/v1/staff/teachers`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 원장이 카드 담당을 바꿀 때(3.16, API 19) 고를 선생님을 보여 준다(API 70). 아직 맡은 카드가 없는 선생님도 나온다. |
| ② 요청 헤더 | Authorization 필수, X-Request-ID 권장. |
| ③ 경로·쿼리 | 없음. 기관은 로그인한 원장의 기관이다. |
| ④ 요청 본문 | 없음. |
| ⑤ 검증·권한 | director만. 같은 기관의 활성 teacher만 돌려준다. 3.16이 배정 대상으로 받는 조건과 같다. |
| ⑥ 정상 응답 | 200 `{items:[{id,display_name,classrooms:[{id,name}]}]}`. 이름·지금 맡은 반만 주고 로그인 ID·연락처는 주지 않는다. |
| ⑦ 오류 응답 | 401 UNAUTHENTICATED, 담임·학부모 403 FORBIDDEN_ROLE. 공통 오류 형식(1.4) 유지. |
| ⑧ 실행 규칙 | 맡은 반은 `classroom_staff`에서 오늘(KST) `valid_from`~`valid_to` 안인 배정만 센다. 기간이 끝난 담임은 목록에 남되 반이 빈 배열이다. 정렬은 이름 → id, 반도 이름 → id(문자 코드 순, mock·DB 같음). 읽기 전용이라 이력·알림을 남기지 않는다. 새 표·마이그레이션은 없다. |

| 필드 | 위치 | 타입 | 필수·빈값 | 설명 |
| --- | --- | --- | --- | --- |
| items[].id | 응답 | string(UUID) | 항상 | 3.16 `assignee_id`에 그대로 넣는 값 |
| items[].display_name | 응답 | string | 항상 | 화면에 보일 이름 |
| items[].classrooms | 응답 | object[] | 항상, 빈 배열 가능 | 지금 맡은 반 `{id,name}`. 맡은 반이 없으면 `[]` |

```json
{"items":[{"id":"00000000-0000-4000-8000-000000000201","display_name":"별빛반 선생님","classrooms":[{"id":"00000000-0000-4000-8000-000000000101","name":"만 4세 별빛반"}]},{"id":"00000000-0000-4000-8000-000000000203","display_name":"보조 선생님","classrooms":[]},{"id":"00000000-0000-4000-8000-000000000202","display_name":"햇님반 선생님","classrooms":[{"id":"00000000-0000-4000-8000-000000000102","name":"만 5세 햇님반"}]}]}
```

### 3.39 [QA 전용] 알림장 다시 시험하기 — `POST /api/v1/qa/daily-notes/reset`

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | QA에서 한 반·한 날짜 알림장을 지우고 초안 만들기부터 다시 시험한다(API 71). 운영에서는 켜지 않는다. |
| ② 요청 헤더 | Authorization 필수, X-Request-ID 권장. |
| ③ 경로·쿼리 | 없음. 기관은 로그인한 교직원의 기관이다. |
| ④ 요청 본문 | `{classroom_id, note_date?}`. 추가 키를 거부한다. 날짜를 생략하면 오늘(KST)이다. |
| ⑤ 검증·권한 | `QA_TOOLS=true` 또는 `1`일 때만 동작한다. 그 반의 현재 담임·같은 기관 원장만 가능하며 필수 동의 검사는 하지 않는다. |
| ⑥ 정상 응답 | 200 `{classroom_id,note_date,deleted:{inputs,notes,cards,notifications,events},unlinked_replies}`. 없거나 이미 지운 대상은 모두 0이다. |
| ⑦ 오류 응답 | 설정이 꺼져 있으면 인증·역할·본문 해석보다 먼저 404 NOT_FOUND. 켜져 있으면 401 UNAUTHENTICATED, 학부모 403 FORBIDDEN_ROLE, 다른 반 담임·다른 기관 반·없는 반 404 NOT_FOUND, 입력 오류 422 VALIDATION_FAILED. 공통 오류 형식(1.4)을 따른다. |
| ⑧ 실행 규칙 | DB는 대상 입력을 FOR UPDATE로 잡고 한 트랜잭션에서 처리한다. 해당 입력의 아이별 알림장과 daily_note_batch 카드, 그 알림·이력·승인을 지운다. 카드 근거·상담 후보는 카드 삭제에 따라 지워진다. 답장 요청은 남기고 source_note_id만 비운다. 기억은 source_card_id만 비운다(승인 답은 문의 답변 카드에서만 생겨 알림장 카드와 연결되지 않는다). 카드→알림장→입력 순서로 삭제하고, FK 없는 tool_called 이력에 tool=qa_daily_note_reset·반·날짜·삭제 개수를 남긴다(0개 초기화도 한 건). deleted.events는 새 감사 기록을 제외한다. 계정·요청·하루 중 기록·기억 본문·다른 반과 날짜는 보존한다. OpenAPI에는 설정과 관계없이 항상 나온다. |

| 필드 | 위치 | 타입 | 필수·빈값 | 설명 |
| --- | --- | --- | --- | --- |
| classroom_id | 요청·응답 | string(UUID) | 필수 | 초기화할 반, 현재 담당 범위 검사 |
| note_date | 요청·응답 | string(date) | 요청 생략 가능, null 불가 | 기본 오늘 KST, 응답에는 항상 포함 |
| deleted.inputs | 응답 | integer | 항상, 0 이상 | 지운 공통 입력 수 |
| deleted.notes | 응답 | integer | 항상, 0 이상 | 지운 아이별 알림장 수 |
| deleted.cards | 응답 | integer | 항상, 0 이상 | 지운 반 묶음 카드 수 |
| deleted.notifications | 응답 | integer | 항상, 0 이상 | card_id 또는 daily_note 주제로 연결된 알림 수 |
| deleted.events | 응답 | integer | 항상, 0 이상 | daily_note_id 또는 card_id가 연결된 이력 수 |
| unlinked_replies | 응답 | integer | 항상, 0 이상 | 요청은 보존하고 source_note_id를 비운 답장 수 |

```http
POST /api/v1/qa/daily-notes/reset
Authorization: Bearer <교직원 토큰>
Content-Type: application/json

{"classroom_id":"00000000-0000-4000-8000-000000000101","note_date":"2026-11-27"}
```

```json
{"classroom_id":"00000000-0000-4000-8000-000000000101","note_date":"2026-11-27","deleted":{"inputs":1,"notes":20,"cards":1,"notifications":2,"events":42},"unlinked_replies":1}
```

### 3.40 [QA 전용] 사람별 QA 원 — API 72~74

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 사람마다 자기 가상 원에서 반복 시험하고, 요청 ID로 오류와 배포 판을 확인해요. 사용 순서는 [QA 안내서](../QA/README.md)를 봐 주세요. |
| ② 요청 헤더 | 72·73은 Authorization 필수, X-Request-ID 권장. 74는 로그인 없이 조회하고, Authorization을 붙이면 `me`(내 역할·원 이름·반 목록)를 더 줘요. |
| ③ 경로·쿼리 | 72 POST `/qa/sandbox/reset`, 73 GET `/qa/traces/{trace_id}`(1~128자 문자열), 74 GET `/qa/info`. 기관은 JWT에서 얻어요. |
| ④ 요청 본문 | 모두 없어요. 초기화 대상 원을 본문으로 고를 수 없어요. |
| ⑤ 검증·권한 | QA_TOOLS=true·1만 열려요. 72는 DB의 sj·ym·jh·ih·tw QA 원 사용자(모든 역할)만 가능해요. QA_PASSWORD가 비어 있어도 404예요. 73은 어떤 역할이든 로그인해야 하고 자기 원 이력·오류만 보여요. |
| ⑥ 정상 응답 | 72는 200 `{org_name,deleted,seeded}`. 73은 200 `{trace_id,events,errors}`이며 없으면 빈 배열 두 개. 74는 200 `{commit,deployed_at,migration,data_backend,switches,qa_orgs,me}`예요. `me`는 토큰이 없거나 틀리면 null이에요. |
| ⑦ 오류 응답 | QA 꺼짐은 인증·입력 해석 전 404 NOT_FOUND. 72의 mock·데모 원·일반 원도 404. 로그인 필요 경로의 미인증은 401 UNAUTHENTICATED, 73의 128자 초과는 422 VALIDATION_FAILED예요. |
| ⑧ 실행 규칙 | 72는 원별 advisory lock과 한 트랜잭션에서 FK 자식부터 원 단위 표를 지우고, 기존 시드로 해당 QA 원 하나를 다시 만들어요. 데모·다른 QA 원 행은 보존해요. 계정 ID·JWT는 유지하고 events에 tool_called, detail.tool=qa_sandbox_reset·삭제 수를 한 건 남겨요. 사진·문서 파일은 남겨요(shortcut: 디스크 정리는 별도 보존 정책 도입 때 처리). 새 기동은 이미 있는 QA 원을 덮지 않아요. 같은 content의 데모 문서 벡터를 먼저 복사하고 빈 벡터만 채워요. 73의 events는 detail.trace_id로 찾아 시각순이며, errors는 API 프로세스의 최근 500건 링 버퍼예요. 배포·재기동 때 errors는 사라지고 worker 예외는 포함하지 않아요. 예외 메시지·입력은 errors에 넣지 않아요. 74는 키·비밀번호·DB 주소를 노출하지 않아요. 같은 QA 서버의 GET `/api/v1/qa/console`은 72~74와 API 71을 버튼으로 부르는 QA 도구 화면(HTML)이에요. API 목록·OpenAPI에는 넣지 않고, QA_TOOLS가 꺼지면 404예요. |

| 필드 | 위치 | 타입 | 필수·빈값 | 설명 |
| --- | --- | --- | --- | --- |
| trace_id | 73 경로·응답 | string | 1~128자 | X-Request-ID 또는 error.trace_id |
| org_name | 72 응답 | string | 항상 | 예: QA 성주 원 |
| deleted | 72 응답 | object(string→integer) | 항상, 각 값 0 이상 | FK 순서로 지운 표별 행 수, 새 감사 기록 제외 |
| seeded | 72 응답 | object | 항상 | users·children·documents의 기준 시드 수 |
| events | 73 응답 | array | 빈 배열 가능 | created_at·action·actor_type·agent_name·request_id·card_id·daily_note_id·detail. 뒤의 ID·agent_name은 null 가능 |
| errors | 73 응답 | array | 빈 배열 가능 | at·method·path·status(500)·error_type·where(파일:줄). 메시지 없음 |
| commit·deployed_at | 74 응답 | string 또는 null | 항상 | GIT_SHA·DEPLOYED_AT, 배포 스크립트가 전달해요 |
| migration | 74 응답 | string 또는 null | 항상 | alembic_version.version_num, mock은 null |
| data_backend | 74 응답 | string | 항상 | mock 또는 db |
| switches | 74 응답 | object | 항상 | daily_note_writer·answer_writer·request_agent 문자열, embedding 불리언, llm_models(설정된 모델 이름만) |
| qa_orgs | 74 응답 | array | 항상 | tag·name·login_prefix. sj·ym·jh·ih·tw 다섯 원 |

```http
POST /api/v1/qa/sandbox/reset
Authorization: Bearer <자기 QA 원 토큰>
```

```json
{"org_name":"QA 성주 원","deleted":{"users":22,"children":21,"documents":69},"seeded":{"users":22,"children":21,"documents":69}}
```

위 deleted 예시는 표 세 개만 줄여 보였어요. 실제 응답에는 모든 원 단위 표가 있어요.

```http
GET /api/v1/qa/traces/qa-example-1
Authorization: Bearer <자기 원 토큰>
```

```json
{"trace_id":"qa-example-1","events":[],"errors":[]}
```

```http
GET /api/v1/qa/info
```

```json
{"commit":null,"deployed_at":null,"migration":null,"data_backend":"mock","switches":{"daily_note_writer":"app.modules.daily_notes.stub_writer:write","answer_writer":"stub","request_agent":"app.modules.requests.agent_stub:run_request","embedding":false,"llm_models":{"default":"gpt-6-luna","supervisor":"","document":"","memory":"","checker":"","code":""}},"qa_orgs":[{"tag":"sj","name":"QA 성주 원","login_prefix":"sj."},{"tag":"ym","name":"QA 영민 원","login_prefix":"ym."},{"tag":"jh","name":"QA 지혜 원","login_prefix":"jh."},{"tag":"ih","name":"QA 인혜 원","login_prefix":"ih."},{"tag":"tw","name":"QA 태웅 원","login_prefix":"tw."}]}
```

### 3.41 [제안] 아이 프로필 사진·급식 참고 사진 — API 75~77

| 칸 | 내용 |
| --- | --- |
| ① 호출 목적 | 아이 동그라미(관찰 기록·알림장 목록·우리 아이·동의 현황·앨범)에 아이 얼굴을, 식단 칸에 그날 점심 참고 사진을 보여 줘요. 사진은 모두 AI로 만든 가상 사진이에요(실제 원아·실제 급식 아님). |
| ② 요청 헤더 | 세 API 모두 `Authorization`(필수), `X-Request-ID`(권장). 화면은 토큰을 붙여 받은 뒤 임시 주소로 바꿔 그려요(`<img src>`에 주소만 넣으면 401). |
| ③ 경로·쿼리 | 75 경로 child_id(UUID). 76 쿼리 `from`·`to`(YYYY-MM-DD, 필수, 62일 안). 77 경로 meal_date(YYYY-MM-DD). 기관은 JWT에서 얻어요. |
| ④ 요청 본문 | 모두 없어요. 사진을 올리는 API는 없고, 시드가 저장소 가상 사진을 넣어요. |
| ⑤ 검증·권한 | 75는 4.2의 아이 범위 규칙과 같아요: 학부모는 보호자로 연결된 아이, 담임은 지금 배정 기간 안의 반 아이, 원장은 같은 기관 아이. 범위 밖·사진 없음은 404와 거부 이력이에요. 76·77은 같은 기관 사용자면 역할과 관계없이 볼 수 있어요. |
| ⑥ 정상 응답 | 75·77은 200 이미지 본문(`image/jpeg`·`image/png`·`image/webp`, `Cache-Control: private, max-age=3600`). 76은 200 `{items:[{meal_date, main_dish, file_url}]}`이며 날짜 오름차순, 없으면 []예요. |
| ⑦ 오류 응답 | 401 UNAUTHENTICATED, 404 NOT_FOUND(범위 밖·사진 없음·파일 없음), 날짜·UUID 형식이 틀리거나 to가 from보다 앞이거나 62일을 넘으면 422 VALIDATION_FAILED. |
| ⑧ 실행 규칙 | 아이 사진은 `children.profile_photo_path`, 급식 사진은 `meal_photos`(기관·날짜 기본 키) 행이 가리키는 MEDIA_DIR 하위 파일(`profiles/`, `meals/<org_id>/`)이에요. 데모 원과 사람별 QA 원은 기동 시드가 `data/fixtures/kg-demo-01/profile_photos`·`meal_photos`의 같은 사진을 넣고, 이미 있는 행·파일은 덮지 않아요. 퇴소 작업은 프로필 경로를 비우고 파일을 지우며, 시드는 퇴소한 아이 사진을 되살리지 않아요. 급식 사진은 그 원 식단표 점심으로 만든 참고 사진이라 화면에 "참고 사진"이라고 밝혀요. |

| 필드 | 위치 | 타입 | 필수·빈값 | 설명 |
| --- | --- | --- | --- | --- |
| child_id | 75 경로 | string(UUID) | 필수 | 사진을 받을 아이 |
| from·to | 76 쿼리 | string(date) | 필수, from ≤ to, 62일 안 | 받을 기간(양 끝 포함) |
| meal_date | 76 응답·77 경로 | string(date) | 필수 | 급식 날짜 |
| main_dish | 76 응답 | string | 항상 | 사진의 주메뉴(예: 수육) |
| file_url | 76 응답·아이 정보의 profile_photo | string | 항상 | 토큰을 붙여 받는 상대 주소(75·77) |

```http
GET /api/v1/meal-photos?from=2026-11-27&to=2026-11-27
Authorization: Bearer <토큰>
```

```json
{"items":[{"meal_date":"2026-11-27","main_dish":"수육","file_url":"/api/v1/meal-photos/2026-11-27/file"}]}
```

```http
GET /api/v1/children/00000000-0000-4000-8000-000000000501/profile-photo
Authorization: Bearer <하늘이 보호자 토큰>
HTTP/1.1 200 OK
Content-Type: image/jpeg
```

## 4. 검증과 권한 규칙

### 4.1 형식 검사(422)와 서버 검사(403·404·409)를 나눈다

| 검사 | 어디서 | 실패하면 | 예 |
| --- | --- | --- | --- |
| 형식: 타입·허용 값·길이·날짜 형식 | Pydantic(`Literal`·`Field`) | 422 `VALIDATION_FAILED` | `type = "unknown"`, `body` 2,001자 |
| 본문 안에서 함께 와야 하는 칸 | Pydantic `model_validator` | 422 | `hold`인데 `hold_until` 없음 |
| 역할 | 서버(인증 의존성) | 403 `FORBIDDEN_ROLE` | 학부모가 카드를 결정하려 함 |
| 소유·범위(기관·반·내 아이) | 서버(DB 조회) | 404 `NOT_FOUND` | 다른 반 카드, 남의 아이 |
| 상태·판·DB 값이 필요한 조건 | 서버(DB 조회) + DB 제약 | 409 | 판이 다름, 회신 전에 완료, 학부모 확인 없이 완료하는데 이유 없음 |

DB 값을 봐야 알 수 있는 조건은 Pydantic에 넣지 않는다. 승인이나 확인 여부를 요청 본문의 값만 믿고 통과시키면 안 되기 때문이다.

```python
# schemas.py — 형식만 본다. 여기서 걸리면 422
class CardDecision(BaseModel):
    version: int = Field(ge=1)
    decision: Literal["approve", "edit_approve", "reject", "hold", "resume", "dismiss", "complete", "escalate", "acknowledge"]
    reason_code: Literal["wrong_fact", "tone", "missing_info", "privacy", "policy",
                         "slot_unavailable", "room_unavailable", "other"] | None = None
    reason_text: str | None = Field(default=None, min_length=1, max_length=500)
    hold_until: date | None = None
    edited_content: dict | None = None

    @model_validator(mode="after")
    def fields_for_decision(self):
        if self.decision in {"reject", "dismiss"} and self.reason_code is None:
            raise ValueError("reason_code")
        if self.decision == "hold" and (self.hold_until is None or self.reason_text is None):
            raise ValueError("hold_until, reason_text")
        if self.reason_code == "other" and self.reason_text is None:
            raise ValueError("reason_text")
        return self
```

```python
# routes.py — 권한·범위·상태는 서버가 DB로 확인한다
@router.post("/cards/{card_id}/decisions")
def decide(card_id: UUID, body: CardDecision, user: User = Depends(current_staff)):
    card = load_card_in_scope(card_id, user)              # 다른 기관·반이면 404
    if card.kind == "director_report" and user.role != "director":
        raise ApiError(403, "FORBIDDEN_ROLE")
    if body.version != card.version:
        raise ApiError(409, "CARD_VERSION_CONFLICT", current_version=card.version)
    request = card.request
    if body.decision == "complete":
        if request.type != "complaint" or request.status != "sent_or_booked":
            raise ApiError(409, "INVALID_TRANSITION")
        if request.parent_confirmed_at is None and body.reason_text is None:
            raise ApiError(409, "REASON_REQUIRED")       # DB 트리거도 한 번 더 막음
    return apply_decision(card, request, body, user)     # 같은 판 두 번이면 DB 유니크 → 409 ALREADY_DECIDED
```

### 4.2 역할별 범위

| 역할 | 볼 수 있는 것 | 할 수 있는 것 |
| --- | --- | --- |
| 학부모 | 자기가 보낸 요청, 자기 아이 앞으로 보낸 알림장, 자기 알림 | 요청 만들기·대화·시간 체크·'확인했어요' 누르기·알림 읽음 처리 |
| 담임 | 우리 반 요청·카드(대체 담임은 `classroom_staff.valid_from~valid_to` 기간 안), 재배정받은 카드, 우리 반 알림장, 원 자료 | 카드 결정(원장 보고 카드 제외)·위험 등급 다시 분류·상담 확정·알림장·자료 올리기·자기 규칙 결정 |
| 원장·원감 | 원 전체 | 카드 결정(원장 보고 카드 포함)·원장 지시·재배정·원장 현황·자료 올리기. 단 민원 회신 카드의 승인·처리 완료는 하지 않으며, 하려 하면 403 `FORBIDDEN_ROLE`. 원장 보고 뒤에도 회신은 담임이 승인하고, 원장은 지시를 남기거나 다른 교사에게 재배정한다 |

모든 조회와 변경은 먼저 토큰의 `org`로 거르고, 그다음에 반·사람 범위를 본다. 범위 밖 자원에는 403이 아니라 404로 답하고, `events`에 `permission_denied`로 남긴다(DB 설계서 4.4). 단, 피드 반 칸에서 같은 기관 사람을 거부할 때는 예외로 403 FORBIDDEN을 쓴다(3.29). 이 규칙은 AI 보안 가드레일 문서의 권한표와 같아야 한다.


## 5. Tool 정의와 호출 흐름

### 5.1 REST API와 Tool

| 구분 | REST API | Tool (Function Calling) |
| --- | --- | --- |
| 부르는 쪽 | 화면(앱·웹) | 에이전트(감독·자료·기억·검사 AI, 코드) |
| 부르는 법 | HTTP 메서드 + 경로 | 도구 이름 + JSON 인자 |
| 권한 | JWT의 역할·기관·반 | 에이전트별 허용 목록 + 요청한 사용자의 권한(5.3) |
| 이 문서에 적는 것 | 요청·응답·상태 코드(2·3장) | 입력·출력·실패 처리·실행 조건(5.4) |

에이전트가 만든 인자도 사용자 입력처럼 다룬다. 그래서 도구 안에서도 REST API와 같은 Pydantic 검사와 범위 검사를 한 번 더 한다. 도구 이름과 인자는 계약표 4장과 팀 자체 30문항을 기준으로 한다.

### 5.2 공통 출력 형식

모든 도구는 성공하든 실패하든 같은 형식으로 돌려준다. 에이전트는 `ok`를 보고 성공인지 가르고, 실패면 `retryable`을 보고 다시 부를지 정한다.

```json
{ "ok": true,
  "data": { "card_id": "00000000-0000-4000-8000-000000000802" },
  "trace_id": "6b0f1c2e-9a7d-4c1e-8f3a-2d5b7e9c1a40" }

{ "ok": false,
  "error": { "code": "UPSTREAM_UNAVAILABLE", "message": "법령 API가 10초 안에 응답하지 않음", "retryable": true },
  "trace_id": "6b0f1c2e-9a7d-4c1e-8f3a-2d5b7e9c1a40" }
```

`trace_id`는 그 요청을 만든 API 호출의 `X-Request-ID`와 같다. 도구 호출은 모두 `events`에 `tool_called` 또는 `tool_failed`로 남긴다. 이때 `detail`에는 도구 이름·`trace_id`·걸린 시간·실패 코드를 넣는다.

**도구 실패 코드**

| `code` | `retryable` | 언제 |
| --- | --- | --- |
| `TOOL_TIMEOUT` | 참 | 도구가 30초 안에 끝나지 않음(6.1) |
| `UPSTREAM_UNAVAILABLE` | 참 | 모델·외부 API(법령·기상) 장애, 429·5xx |
| `SAVE_FAILED` | 참 | DB 저장이 일시적으로 실패함(연결 끊김·잠금 대기 초과). 30문항 F04의 `save_failed`에 해당 |
| `NOT_FOUND` | 거짓 | 대상이 없거나 이 요청의 기관·반 밖에 있음 |
| `VALIDATION_FAILED` | 거짓 | 인자 형식이 틀림(허용 밖 `doc_type`·`topic_key` 등) |
| `FORBIDDEN_SCOPE` | 거짓 | 이 에이전트에 허용되지 않은 도구이거나, 요청한 사용자가 할 수 없는 일 |
| `SLOT_TAKEN` · `SLOT_NOT_CHOSEN` | 거짓 | 상담 확정 충돌(3.4와 같음) |
| `INVALID_TRANSITION` | 거짓 | 지금 상태에서 할 수 없는 일(예: 끝난 요청에 카드 만들기) |

### 5.3 도구를 실행하기 전에 서버가 확인하는 네 가지

| 확인 | 방법 | 실패하면 |
| --- | --- | --- |
| ① 에이전트 허용 목록 | 5.4의 '부르는 AI' 열에 없는 도구는 부르지 못함. 이 열은 에이전트를 다섯으로 나눈 뒤(T43)부터 적용한다. 그 전 단계의 단일 에이전트(T29)는 에이전트가 하나뿐이라 `book_slot`을 뺀 도구를 모두 부른다(30문항이 `find_consult_slots`·`search_documents` 직접 호출을 채점) | `FORBIDDEN_SCOPE` |
| ② 요청한 사용자의 권한 | 학부모 요청에서 나온 호출은 그 학부모가 볼 수 있는 범위 안에서만 실행. 교직원용 도구(`book_slot`)는 담임의 확정 API 안에서만 부름 | `FORBIDDEN_SCOPE` |
| ③ 데이터 소유권 | 기관·반·학부모 ID는 모델이 인자로 넣지 않고, 백엔드가 지금 요청에서 꺼내 채움(계약표 4장의 '(백엔드)' 값). 모델이 다른 ID를 넣더라도 범위 밖이면 거부 | `NOT_FOUND` |
| ④ 사람 승인 상태 | 학부모에게 나가는 일(회신 발송·예약 확정·알림장 발송)은 도구로 하지 않고, 담임의 결정 API가 승인 기록(`approvals`)을 남긴 뒤에만 일어난다. 담임이 이미 승인해 둔 '원에 남은 답'도 학부모에게 바로 보내지 않고 담임 카드의 답변 초안으로만 쓴다(5.7). 못 하는 일을 알리는 고정 안내만 승인 없이 대화에 남긴다(5.7) | 도구 목록에 없음 |

### 5.4 도구 목록과 실패 후 처리

아래 표는 계약표 4장에 있는 도구마다 실패 코드와 실패 후 처리를 적은 것이다. '실패 후 처리' 열은 기본값이다. `retryable`이 참이면 1번 다시 부르고, 그래도 실패하거나 `retryable`이 거짓이면 사람 카드로 넘긴다. 에이전트별 세부 행동은 T14 에이전트 명세 6장에 있다.

| 도구 | 부르는 AI | 실행 조건 | 성공 `data` | 실패 코드 | 실패 후 처리(기본) |
| --- | --- | --- | --- | --- | --- |
| `route_request` | 감독 | 요청이 `received`·`classified` | 분류 결과를 저장 | `UPSTREAM_UNAVAILABLE`·`SAVE_FAILED`(참), `INVALID_TRANSITION`(거짓) | 1번 다시 → 실패면 코드로 위험·분류를 다시 저장하고 담임에게 초안 없는 사람 카드로 넘김. 긴급·판단 필요면 원장 보고도 만듦(6.3). 유효한 담임이 없을 때만 미배정 |
| `create_card` | 감독·자료 | 요청이 끝나지 않음 | `card_id` | `SAVE_FAILED`(참), `VALIDATION_FAILED`·`INVALID_TRANSITION`(거짓) | 1번 다시 → 실패면 학부모에게 '말씀하신 내용은 받았는데 선생님께 넘기는 중에 저장 오류가 났어요. 확인이 늦어질 수 있으니 급하시면 원으로 전화 주세요'라고 솔직히 안내('선생님께 전달했어요'라고 하지 않음, 30문항 YC-F04). 요청은 `POST /requests` 단계에서 이미 저장돼 '내 요청' 화면에 '접수됨'으로 보이므로, '접수가 안 됐어요'라고도 하지 않음. 카드는 서버 점검 작업이 코드 위험·담임 배정을 적용해 다시 올림(6.3). 유효한 담임이 없을 때만 미배정 |
| `notify_staff` | 감독 | 카드가 있음 | `notification_id` | `SAVE_FAILED`(참), `NOT_FOUND`(거짓) | 1번 다시 → 실패해도 카드는 받은함에 그대로 남음. 긴급·판단 필요 카드면 `warnings[]`에 `notify_failed`를 붙여 카드에서 눈에 띄게 하고, 이력에도 남김 |
| `search_documents` | 자료 | 요청한 기관의 자료만, 학부모면 원 전체 + 아이 반 자료 | `chunks[]` | `TOOL_TIMEOUT`·`UPSTREAM_UNAVAILABLE`(참), `VALIDATION_FAILED`·`NOT_FOUND`(거짓) | 1번 다시 → 실패하거나 근거가 없으면 추측하지 않고 담임 카드로 넘김(`no_evidence`) |
| `get_law_article` | 자료 | 법령 이름·조문이 있음 | `text`, `source_url`, `fetched_at` | `UPSTREAM_UNAVAILABLE`(참), `NOT_FOUND`(거짓) | 1번 다시 → 실패면 법령 인용 없이 초안을 쓰고, 카드에 '법령 확인 못 함' 표시 |
| `get_memory` | 기억 | 기억의 주인이 요청 담당자 | `memories[]`, `active_rules[]` | `SAVE_FAILED`(참) | 1번 다시 → 실패면 기억 없이 진행 |
| `propose_rule` | 기억 | 같은 주인·같은 이유 코드가 3번(마지막 decline 뒤에 쌓인 새 기억만 셈). rule_json은 객체, after·before는 HH:MM | `rule_id`(이미 있으면 기존 ID) | `SAVE_FAILED`(참), `VALIDATION_FAILED`(거짓) | 1번 다시 → 실패면 제안만 되돌리고 tool_failed 기록(카드 거절·기억은 유지하고, 다음에 다시 셈) |
| `check_draft` | 검사 | 초안이 있는 카드·알림장 | 검사 결과를 저장 | `TOOL_TIMEOUT`·`UPSTREAM_UNAVAILABLE`(참) | 1번 다시 → 실패면 '검사 못 함'을 표시하고 사람 카드로 넘김 |
| `return_to_step` | 검사 | `check_attempts` < 2 | `attempt` | `INVALID_TRANSITION`(거짓, 3번째) | 3번째에는 오류를 내는 대신 사람 카드로 넘김(FR-08) |
| `find_consult_slots` | 코드 | 상담 요청이고 담임 일정이 있음 | `slots[]`(회차마다 최대 3개) | `TOOL_TIMEOUT`·`SAVE_FAILED`(참), `NOT_FOUND`(거짓) | 1번 다시 → 실패면 시간을 지어내지 않고 '지금 확인할 수 없음' 안내(30문항 YC-F01). 빈 목록이면 다른 날을 묻거나 담임 카드로 넘김 |
| `request_consultation` | 감독 | 상담 요청이 `needs_info` | `slots[]`, `request_status` | `SAVE_FAILED`(참), `INVALID_TRANSITION`(거짓) | 1번 다시 → 실패면 학부모에게 화면에서 다시 고르도록 안내 |
| `book_slot` | 코드 | 담임 확정 API 안에서만 | `booking_id` | `SLOT_TAKEN`·`SLOT_NOT_CHOSEN`(거짓), `SAVE_FAILED`(참) | 담임 화면에 409를 그대로 보여 주고 후보를 다시 내도록 안내 |
| `get_my_requests` | 감독 | 요청한 학부모 본인 것만 | `items[]` | `SAVE_FAILED`(참) | 1번 다시 → 실패면 '요청 목록 화면에서 확인' 안내 |
| `get_daily_note` | 감독 | 요청한 학부모의 아이, 보낸 알림장만 | `note` 또는 없음 | `NOT_FOUND`(거짓) | 없으면 '아직 안 보냄' 안내 |
| `find_saved_answer` | 감독 | 근거 문서가 모두 최신 | `saved_answer_id`, `similarity`, `sources_current` | `TOOL_TIMEOUT`(참) | 실패하면 원에 남은 답 없이 평소대로 처리 |

### 5.5 먼저 쓰는 도구 — 입력·결과·실패와 실행 전 확인

먼저 채우는 도구는 세 개다. 첫 시연인 알림장에 쓰는 도구와, 모든 요청이 거치는 사람 인계에 쓰는 도구다. 입력은 이름·타입·필수·허용값으로, 결과는 결과 ID·상태·업무상 의미로 적는다. 실패는 형식·권한·충돌·일시 오류로 나누고, 다시 시도하는지와 최대 횟수, 그 뒤에 할 행동과 화면 문구를 적는다.

알림장의 두 도구는 Function Calling 도구가 아니다. 알림장 그래프(`agents/graphs/daily_note.py`)가 모델에게서 JSON 한 덩어리를 받아 오는 호출이고, 저장·상태·이력은 백엔드 실행기(`apps/api/app/modules/daily_notes/runner.py`)가 맡는다. 그래프는 `DAILY_NOTE_WRITER=graph`일 때 쓴다. 기본값은 모델 없이 입력만 옮기는 대역이다. 서버는 두 도구를 실행하기 전과 결과를 저장하기 전에 5.3의 네 가지를 이렇게 확인한다.

| 확인 | 알림장에서 하는 일 |
| --- | --- |
| ① 입력·허용 도구 | 아이 줄 쓰기는 자료 AI 모델(`LLM_MODEL_DOCUMENT`)로, 검사는 검사 AI 모델(`LLM_MODEL_CHECKER`)로만 부른다. 반 입력은 3.19의 형식 검사를 통과한 값만 들어간다 |
| ② 사용자·소유권 | 담임의 현재 담당 반인지는 API가 먼저 본다(3.19 ⑤). 모델에 넘기는 입력은 백엔드가 그 기관·그 반의 아이, 그 아이 보호자의 그날 요청, 공개 범위가 맞는 식단만 골라 만든다. 모델의 답도 저장하기 전에 다시 본다. 입력에 없는 아이나, 다른 아이의 요청·입력에 없는 문서를 출처로 쓴 답이면 그 아이 알림장을 `draft_failed`로 바꾼다 |
| ③ 필요한 승인 | 두 도구는 초안과 확인 항목을 저장할 뿐 학부모에게 보내지 않는다. 학부모에게는 담임이 확인(3.21)하고 보내기(3.6)를 해야 나간다 |
| ④ 중복과 저장 결과 | 같은 반·같은 날짜의 작업은 하나뿐이다(3.19 ⑤). 저장하기 직전에 이 실행이 아직 최신인지 다시 확인해, 그 사이 다시 만들기가 시작됐으면 이 결과를 버린다. `ready`·`sent`이거나 담임이 고친 알림장은 덮어쓰지 않는다. 제한 시간(`DAILY_NOTE_WRITER_TIMEOUT`)이 지난 뒤 도착한 결과도 저장하지 않는다 |

#### 5.5.1 알림장 아이 줄 쓰기 — 자료 AI(`write()`)

프롬프트는 `agents/prompts/documents.md`의 '알림장 초안 쓰기' 절이다. 아이 메모나 그날 보호자 요청이 있는 아이마다 부른다. 둘 다 없는 아이는 모델을 부르지 않고 반 공통 줄만 둔다. 그래프의 `draft_daily_notes()`는 `ThreadPoolExecutor`로 아이별 쓰기·검사를 동시에 처리하고, `NOTE_DRAFT_CONCURRENCY`로 최대 동시 아이 수를 정한다(기본값 5, 최솟값 1). 한 아이 안에서는 쓰기→코드 검사→검사 AI→필요하면 다시 쓰기 순서로 진행하며, 결과 목록은 입력 아이 순서를 유지한다.

| 입력 | 타입 | 필수 | 허용값·설명 |
| --- | --- | --- | --- |
| `note_date` | string(date) | 필수 | 알림 날짜 |
| `classroom` | object | 필수 | `{ id, name }` |
| `activities`·`supplies` | string | 필수 | 반 활동(1~2,000자)·준비물(빈 문자열 가능) |
| `menu` | string 또는 null | 필수 | 그날 쓸 식단 본문. 없으면 null |
| `child_name`·`child_memo` | string | 필수 | 아이 표시 이름과 담임 메모. 메모가 없으면 `""` |
| `requests[]` | object[] | 필수 | `{ request_id, type, text }`. `type`은 `medication`·`pickup`(서버가 문의는 보내지 않는다) |
| `review_issues[]` | object[] | 필수 | 검사 AI가 돌려보낸 확인 항목. 처음에는 `[]` |

결과는 `{"child": "아이 메모 줄 또는 null", "requests": [{"request_id", "value", "answered"}]}`이다. 코드는 이 결과를 아이 메모 줄(출처 `teacher_input`)과 보호자 요청 줄(출처 `request`)로 바꾸고, 입력에 없는 `request_id`는 버린다. 반 공통 줄(`day`·`supplies`·`meal`)은 모델이 아니라 코드가 만든다. 저장하고 나면 결과 ID는 아이별 알림장 ID(3.20 `items[].id`)가 된다. 상태는 확인 항목이 있으면 `needs_check`, 없으면 `draft`다. 업무상으로는 담임이 고치고 확인할 초안이 생겼다는 뜻이다.

| 실패 구분 | 언제 | 다시 하나 | 최대 횟수 | 그 뒤 | 담임 화면 문구 |
| --- | --- | --- | --- | --- | --- |
| 일시 오류 | 시간 초과·429·5xx·연결 오류 | 예 | 모델 호출 안에서 2번(1초 → 2초, 6.2) | 그 아이 알림장에 `draft_failed`를 남기고 담임에게 넘긴다. 다른 아이 초안은 그대로 저장한다 | "이 아이 초안을 만들지 못했어요. 다시 시도하거나 직접 써 주세요." |
| 형식 오류 | JSON이 아닌 답 | 예 | 1번 더 묻는다 | 위와 같다 | 위와 같다 |
| 요청 오류 | 모델 API의 400·401·403·422 | 아니요 | 0 | 위와 같다 | 위와 같다 |
| 소유권 | 입력에 없는 아이·요청·문서를 출처로 씀 | 아니요 | 0 | 저장 전 검사에서 그 아이를 `draft_failed`로 바꾼다 | "아이 메모 초안을 만들지 못했어요. 직접 확인해 주세요" |
| 충돌 | 실행 중에 다시 만들기가 시작됐거나 담임이 그 아이 알림장을 고치거나 확인함 | 아니요 | 0 | 이 실행 결과를 버리거나 그 아이를 건너뛴다 | 없음. 화면은 최신 상태를 다시 읽는다 |

시험은 `test_writer_fails_twice_gives_draft_failed`, `test_writer_retry_once_then_succeeds`, `test_transport_failure_is_not_asked_again_in_graph`, `test_model_retries_only_retryable_errors_with_backoff`(`tests/unit/test_daily_note_graph.py`)와 `test_one_child_failure_keeps_other_children_and_blocks_batch`, `test_regenerate_supersedes_active_writer_success_or_failure`(DB)다.

#### 5.5.2 알림장 초안 검사 — `check_draft`(검사 AI, `review()`·`code_checks()`)

프롬프트는 `agents/prompts/checker.md`의 '알림장: 메모와 대조한다' 절이다. 5.5.1이 아이 한 명의 줄을 쓸 때마다 부른다.

| 입력 | 타입 | 필수 | 허용값·설명 |
| --- | --- | --- | --- |
| `activities`·`supplies`·`menu` | string(`menu`는 null 가능) | 필수 | 5.5.1과 같다 |
| `child_memo` | string | 필수 | 담임 메모 |
| `requests[]` | object[] | 필수 | 5.5.1과 같다 |
| `draft[]` | object[] | 필수 | 5.5.1이 쓴 줄 `{ key, label, value, source }` |

모델의 결과는 `{"checks": [{"item_key", "kind", "problem", "sentence"}]}`이고, `kind`는 `not_in_memo`·`sensitive`·`other_child`·`date_check`·`absent` 다섯 값만 받는다. 여기에 코드가 다른 아이 이름(`other_child`), 보호자 요청 누락(`request_missed`), 투약 요청·옮기지 않은 메모·답하지 못한 문의(`sensitive`)를 더한다. 이렇게 합친 항목을 `open_checks[] { id, item_key, kind, problem, sentence, request_id? }`로 저장한다. 결과 ID는 확인 항목 ID(`open_checks[].id`, 저장할 때 UUID로 바꾼다)이고, 항목이 하나라도 있으면 알림장 상태는 `needs_check`다. 업무상으로는 담임이 보내기 전에 꼭 봐야 할 곳이라는 뜻이다. 항목이 남아 있으면 발송이 잠긴다(3.19.1).

`not_in_memo`는 검사 AI가 아이 메모 줄을 메모·반 공통·식단과 대조해 근거 없는 사실·이유·평가나 반 활동을 그 아이가 했다는 서술을 찾은 결과다. 병명·"괜찮아요" 같은 낱말을 고정 금지어 목록과 대조하는 코드는 없다. `code_checks()`는 메모·아이별 초안에 있는 다른 아이 이름과 요청별 출처 누락을 검사하고, 초안에 옮긴 투약 요청에는 `sensitive`를 남긴다. 메모 줄 누락과 답하지 못한 문의는 각각 `memo_left_out()`·`unanswered()`가 `sensitive`로 넘긴다. 쓰기·검사 실패는 `draft_failed`·`check_failed`이며, 백엔드는 작성기가 준 `return_limit`도 확인 항목으로 보존한다(3.7·3.20·3.21).

| 실패 구분 | 언제 | 다시 하나 | 최대 횟수 | 그 뒤 | 담임 화면 문구 |
| --- | --- | --- | --- | --- | --- |
| 일시 오류·요청 오류 | 5.5.1과 같다 | 5.5.1과 같다 | 5.5.1과 같다 | 검사를 통과로 치지 않고 `check_failed`를 남긴 채 담임에게 넘긴다. 이미 쓴 초안은 지우지 않는다 | "메모와 대조하는 검사가 끝나지 않았어요. 직접 읽고 확인해 주세요." |
| 형식 오류 | JSON이 아니거나 `checks` 목록이 없음 | 예 | 1번 더 묻는다 | 위와 같다 | 위와 같다 |
| 허용 밖 값 | `kind`가 다섯 값 밖 | 아니요 | 0 | 그 항목만 버린다 | 없음 |
| 고칠 수 있는 문제 | `not_in_memo`·`request_missed`가 나옴 | 예. 5.5.1로 돌려보낸다(5.4의 `return_to_step`) | 2번 | 그래도 남으면 확인 항목을 그대로 둔 채 넘긴다 | 항목마다 `problem` 문장 |

시험은 `test_checker_fails_twice_gives_check_failed_and_keeps_draft`, `test_returns_stop_after_two_and_leave_check`, `test_missing_request_is_returned_then_fixed`, `test_unknown_kind_from_checker_is_ignored`(`tests/unit/test_daily_note_graph.py`)다.

#### 5.5.3 사람 인계 카드 — `create_card`

아래는 모델에게 보이는 정의다. 백엔드가 채우는 값(`request_id`·`kind`·`assignee_id`)은 정의에 넣지 않는다. `description`은 모델이 이 도구를 언제 쓸지 판단하는 근거이므로 구체적으로 쓴다.

```json
{
  "name": "create_card",
  "description": "학부모 문의·민원을 담임(또는 원장) 받은함에 사람 확인 카드로 올린다. 자동 회신 대신 쓴다. 근거가 없거나 문서끼리 다르거나 위험해 보이면 반드시 이 도구로 사람에게 넘긴다.",
  "parameters": {
    "type": "object",
    "properties": {
      "request_type": { "type": "string", "enum": ["inquiry", "complaint"] },
      "topic_key": { "type": "string", "enum": ["safety", "meal", "teacher", "belongings", "fee", "pickup_bus",
                                                 "peer_conflict", "health_hygiene", "photo_record", "communication", "other"] },
      "summary": { "type": "string", "maxLength": 300 },
      "urgency": { "type": "string", "enum": ["normal", "urgent"] },
      "escalate_to_director": { "type": "boolean" }
    },
    "required": ["request_type", "topic_key", "summary", "urgency", "escalate_to_director"],
    "additionalProperties": false
  }
}
```

입력의 이름·타입·허용값은 위 정의에 있다. 모델은 다섯 칸만 채우고, `request_id`·`kind`·`assignee_id`는 백엔드가 지금 요청에서 꺼내 채운다(5.3 ③). 이 도구는 요청이 아직 끝나지 않았을 때(`received`·`classified`·`assigned`·`needs_info`) 부른다. 근거 없음·문서 충돌·민원에 해당하면 반드시 이 도구로 사람에게 넘긴다.

결과는 `{"ok": true, "data": {"card_id": "…"}, "trace_id": "…"}`이고, 결과 ID는 `card_id`다. 카드는 담당 담임이 있으면 `pending`, 없으면 `unassigned`이고, 요청은 `awaiting_review`가 된다. 긴급·판단 필요이거나 세 번째 반복 민원이면 원장 보고 카드도 만들고, 요청은 `escalated`가 된다. 업무상으로는 사람이 확인할 카드가 받은함에 생겼고, 학부모에게는 아직 답이 나가지 않았다는 뜻이다.

| 실행 전 확인 | `create_card`에서 하는 일 |
| --- | --- |
| ① 입력·허용 도구 | 감독·자료 AI만 부른다(5.4). 인자는 위 정의로 다시 검사한다 |
| ② 사용자·소유권 | 학부모 요청에서 나온 호출이면 그 학부모가 볼 수 있는 범위 안에서만 만든다. 요청·기관·반은 모델 인자가 아니라 백엔드 값으로 정한다 |
| ③ 필요한 승인 | 카드는 사람 확인을 기다리는 일이라 승인 없이 만든다. 학부모에게 나가는 일은 담임 결정 API만 한다(5.3 ④) |
| ④ 중복과 저장 결과 | 요청 행을 잠근 뒤, 같은 요청에 카드가 이미 있으면 새로 만들지 않는다 |

| 실패 구분 | `code` | `retryable` | 최대 횟수 | 그 뒤 | 학부모 안내 |
| --- | --- | --- | --- | --- | --- |
| 형식 | `VALIDATION_FAILED` | 거짓 | 0 | 사람 카드로 넘긴다(5.4 기본) | — |
| 권한·소유권 | `FORBIDDEN_SCOPE`·`NOT_FOUND` | 거짓 | 0 | 위와 같다 | — |
| 충돌 | `INVALID_TRANSITION`(이미 끝난 요청) | 거짓 | 0 | 카드를 만들지 않는다 | — |
| 일시 오류 | `SAVE_FAILED` | 참 | 1 | 그래도 실패하면 실행기나 점검 작업이 담당자 없는 카드를 만든다(6.3) | "말씀하신 내용은 받았는데 선생님께 넘기는 중에 저장 오류가 났어요. 확인이 늦어질 수 있으니 급하시면 원으로 전화 주세요." |

쓰기 응답이 끊겼다면 카드가 이미 저장됐을 수 있다. 그래서 다시 부르기 전에 그 요청에 카드가 있는지 먼저 확인한다. 지금 실행기와 점검 작업도 요청을 잠근 뒤 카드가 있는지 다시 읽고 나서 카드를 만든다.

**지금 코드.** 요청 처리 입구는 `apps/api/app/modules/requests/agent_stub.py`다. 기본 설정은 낱말 분류·대역 초안이고, `LLM_MODEL_SUPERVISOR`를 채우면 모델 분류 제안을 검증하며 `ANSWER_WRITER=graph`면 자료·검사 AI를 호출한다. 모델이 이 `create_card` 도구 계약을 직접 호출하는 경로와 T43 협업 그래프는 아직 연결하지 않았다. 대역은 이 도구를 부르지 않고 `new_card()`로 카드를 바로 저장한다. 저장 중 예외가 나면 실행기(`runner.py`)는 모델을 다시 부르지 않고 코드 규칙 `request_rules.classify(type, body)`로 주제·긴급도·위험 등급·종류를 다시 저장한다. 정상 경로와 같은 쿼리로 현재 유효한 담임을 골라 초안 없는 회신 카드를 배정한다. 일반은 `awaiting_review`와 담임 `new_card` 알림, 긴급·판단 필요는 원장 보고 카드·`escalated`와 담임·원장 위험 알림으로 넘긴다. 유효한 담임이 없을 때만 회신 카드가 `unassigned`다. 이때 이력에는 실패 원인과 상관없이 `tool_failed`·`UPSTREAM_UNAVAILABLE`로 기록된다. 위 학부모 안내 문장도 아직 코드에 없어서, 학부모 화면에는 상태 표시 이름만 보인다(6.7 마지막 사례). 시험은 `test_agent_failure_preserves_request_and_hands_off_without_private_error`, `test_stub_transaction_rolls_back_then_handoff_once`, `test_sweep_exact_age_states_card_exclusion_and_concurrent_idempotency`(`tests/integration/db/test_requests.py`)다.

### 5.6 호출 흐름

아래는 요청 하나가 거치는 순서다. 모든 단계가 같은 `trace_id`를 이어 쓰므로, 로그와 LangSmith에서 요청 하나의 흐름을 한 번에 따라갈 수 있다.

| 순서 | 누가 | 하는 일 | 쓰는 도구·API |
| --- | --- | --- | --- |
| 1 | 화면 → API | 인증, 입력 형식 검사, 요청 저장, 202 응답 | `POST /requests` |
| 2 | 감독 AI | 유형·급한 정도·위험 등급·주제·`out_of_scope_kind`를 분류하고 빠진 정보 확인. 아래 5.7의 고정 안내 대상 문의는 여기서 안내를 남기고 끝냄 | `route_request` |
| 3 | 자료 AI · 코드 · 기억 AI | 문의면 근거를 찾아 초안 작성, 상담이면 후보 계산, 거절 이력은 기억에서 조회 | `search_documents`·`get_law_article`·`find_consult_slots`·`get_memory` |
| 4 | 검사 AI | 출처·날짜·대상·누락·민감정보를 대조하고, 최대 2번까지 앞 단계로 돌려보냄 | `check_draft`·`return_to_step` |
| 5 | 감독 AI | 사람 확인 카드를 만들고, 긴급이거나 3번째 반복된 민원이면 원장에게 보고 | `create_card`·`notify_staff` |
| 6 | 흐름 멈춤 | 카드가 사람 결정을 기다림(LangGraph interrupt, 체크포인트는 `cards.graph_thread_id`) | — |
| 7 | 담임·원장 → API | 결정을 보내면 서버가 역할·범위·판·상태를 확인하고 승인 기록을 남김 | `POST /cards/{id}/decisions`·`bookings` |
| 8 | 서버 | 회신 발송·예약 확정·알림 보내기, 이력 기록 | `book_slot`(확정 API 안), 알림 발송기 |

### 5.7 업무 흐름 세 개 — 경로·도구·권한·DB 상태

**사람에게 넘기고 자동 답변하지 않는 기준.** 다음 경우에는 학부모에게 답을 보내지 않고, 초안 없는 사람 카드로 넘긴다. 긴급(`risk_level = urgent`)인 문의·민원, 근거 없음(`no_evidence`), 문서 충돌, 검사 AI가 2번 돌려보낸 뒤에도 통과하지 못한 경우(3번째, FR-08)다. 판단 필요(`uncertain`)는 초안을 미리 써 두지만, 담임·원장이 일반이나 긴급으로 다시 분류하기 전에는 승인할 수 없다(3.3). 권한 밖 요청은 아래 고정 안내 조건을 먼저 확인하고, 조건에 맞지 않으면 평소 담임 흐름을 따른다. 권한 밖 자료는 읽지 않으며, 카드도 현재 사용자의 범위 안에서만 만든다. 내용에 대한 답은 담임 결정 API가 승인 기록(`approvals`)을 남긴 뒤에만 나간다(5.3 ④). 못 하는 일에 대한 고정 안내는 아래 조건에서 승인 없이 남긴다. 접수 안내와 정보 되묻기는 여기서 말하는 답변 발송과 구분한다. **원에 남은 답도 예외가 아니다.** 원에 남은 답은 담임이 이미 승인해 저장해 둔 문의 답이다(FR-20). 감독 AI가 `find_saved_answer`로 찾은 답의 `similarity`가 기준 이상이고 `sources_current = true`이며 요청이 긴급·판단 필요가 아니면, 그 답과 출처를 담임 카드의 답변 초안으로 쓴다. 학부모에게는 담임이 승인한 뒤에 나가고, 어느 답을 썼는지는 이력에 `saved_answer_id`로 남긴다. `similarity` 기준값은 평가 뒤에 정한다.

**권한 밖 고정 안내(Y-098).** 감독 AI 제안을 검증한 `out_of_scope_kind`는 `payment`·`others_privacy`·`other_family`·`other_teacher` 또는 null이다. 권한 밖인지와 종류는 감독 AI가 정하고(우리 아이 일이나 안전·건강이 섞이면 `null`로 두라는 원칙을 지침에 준다), 코드는 값이 목록 안인지만 본다. 긴급·판단 필요면 바로 안내하지 않는다. 모델이 없거나 실패했을 때만 낱말 대역(`request_rules.scope_kind`)이 정규식으로 종류를 잡고, 이때 주제(`topic_key`)가 `peer_conflict`·`safety`·`health_hygiene`이거나 본문에 “우리 아이”·“우리 애”·“저희 아이”가 있으면 종류를 두지 않는다. 예를 들어 “다른 아이랑 다퉜다는데 무슨 일인지 알려주세요”는 갈등 주제로 담임에게 간다. 조건을 통과한 문의만 아래 고정 문구를 `request_messages(sender_type='agent', sender_id=null)`로 남기고 `sent_or_booked`로 둔다. 담임 승인 카드·승인 기록은 만들지 않고 `out_of_scope_answered` 이력의 `detail.kind`에 종류를 남기며, 학부모에게 `sent_or_booked` 알림을 보낸다. DB 기본 입구에서는 자료·검사 AI와 공공 자료 조회를 건너뛴다. 응답 메시지는 `sender_role=null`이다.

| `out_of_scope_kind` | 학부모 대화에 남기는 고정 문구 |
| --- | --- |
| `payment` | 유치온에서는 원비 결제를 하지 않아요. 원비는 원에서 안내한 기존 방법으로 문의해 주세요. |
| `others_privacy` | 다른 가정의 연락처 같은 개인정보는 알려 드릴 수 없어요. |
| `other_family` | 다른 가정의 요청이나 내용은 볼 수 없어요. 우리 아이 일이라면 다시 적어 주세요. |
| `other_teacher` | 상담은 담임 선생님과 잡을 수 있어요. |

상담은 같은 보호 조건을 통과한 `other_teacher`일 때만 안내 메시지를 더하고, 담임 `consult_slots`·시간 선택·예약 확정은 그대로 둔다. 그 밖의 상담과 모든 민원은 이 종류를 바로 안내에 쓰지 않는다. 안내 뒤 학부모가 글을 더 남기면 3.10 규칙에 따라 초안 없는 담임 회신 카드가 생긴다(담임이 없으면 미배정·원장 알림). 교직원은 요청 이력·대화를 볼 수 있다. 공용 HTTP 시험은 `test_out_of_scope_*`와 `test_followup_to_cardless_answer_creates_empty_reply`, DB 중복 실행·트랜잭션 시험은 `tests/integration/db/test_requests.py`의 `test_out_of_scope_*`다.

**위험 등급은 문의·상담·민원에 함께 붙는다.** 보호자 글을 받는 이 세 유형에는 같은 규칙으로 위험 등급(일반·긴급·판단 필요)을 매기고, 투약·귀가에는 붙이지 않는다(기획서 FR-03). 규칙이 같으니 문의도 긴급이나 판단 필요로 나오면 민원과 같은 길로 간다. 담임 카드와 원장 보고 카드를 만든 뒤 요청을 `escalated`로 둔다. 긴급은 자료·검사 AI를 부르지 않고 초안 없이 넘기고, 판단 필요는 초안을 써 두되 다시 분류하기 전에는 승인을 막는다. 상담은 다르다. 시간 고르기(`consult_slots`, 요청 `needs_info`)와 담임 확정은 그대로 두고, 원장 보고 카드와 위험 알림만 더한다. 위험 알림은 민원 때와 마찬가지로 담임과 원장이 받고, 원장 보고 카드는 담임이 예약을 확정하거나 상담을 반려할 때 함께 닫힌다(3.4). 위험 등급은 감독 AI가 정하고(판단 필요면 이유 한 줄 `risk_reason`도 쓴다), 코드는 값이 목록 안인지만 본다. 코드가 지키는 선은 둘이다. 아이 몸에 해가 간 명백한 표현(다침·피·때림·학대 등, `request_rules.child_harm`)은 AI가 뭐라 해도 긴급으로 올리고, AI가 올린 위험은 낱말로 내리지 않는다. 낱말 대역(`apps/api/app/core/request_rules.py`)은 모델이 없거나 실패했을 때와 모의 API에서만 쓰며, 낱말 하나가 아니라 '안전을 확인'·'신고하겠'·'경찰에'·'유출' 같은 짧은 구를 본다. 민원을 '안전'·'신고'·'개인정보' 낱말 하나로 긴급으로 올리던 규칙과, 본문의 '판단 필요' 글자로 등급을 정하던 규칙은 없앴다. 대역은 판단 필요를 만들지 않는다. 시험은 `test_risk_words_by_phrase_for_every_guardian_request_type`·`test_single_words_do_not_raise_risk_in_fallback`(`tests/unit/test_request_rules.py`), `test_child_harm_line_raises_model_risk`(`tests/unit/test_request_supervisor.py`), `test_high_risk_handoff_has_two_cards_and_no_automatic_reply`·`test_risky_consultation_keeps_slot_flow_and_adds_director_report`(`tests/integration/api/test_complaints.py`), `test_risky_inquiry_skips_answer_model_and_saves_risk`(`tests/integration/db/test_request_risk_types.py`)다.

아래 표의 API 경로 앞에는 모두 `/api/v1`을 붙인다. 도구의 전체 입력·출력은 계약표 4장을, 실행 조건과 실패 코드는 5.4를 따른다. 표의 도구 호출은 설계상의 계약이고, 모의 API는 같은 흐름을 메모리 안에서 흉내 낸다. DB 제약은 DB 스키마 설계서(T09)를 기준으로 한다.

**문의 답변**

| 단계 | 누가 | API·도구 | 입력 → 출력 | 권한(누가 할 수 있나) | DB 상태 변화(`requests.status`·`cards.status`·제약) | 실패하면 |
| --- | --- | --- | --- | --- | --- | --- |
| 접수·분류 | 학부모·감독 AI | `POST /requests`, `route_request` | `client_request_id`, `type=inquiry`, `body`, `child_id` → `request { id, status, stream_url }` | 학부모 본인 아이, 기관·반은 서버가 채움 | 요청 `received → classified → assigned`, `(requester_id, client_request_id)` 유니크 | 역할이 틀리면 403 `FORBIDDEN_ROLE`, 남의 아이면 404 `NOT_FOUND`. 같은 제출이 다시 오면 200 + 기존 요청 |
| 근거·검사 | 자료·검사 AI | `search_documents`, `check_draft` | `kindergarten_id`, `doc_type`, `query` → `chunks[]`; `card_id` → 검사 결과 | 기관·아이 반 자료만, AI 허용 목록(5.3 ①) | `cards.kind=reply_draft`, 카드 `pending`, `cards.draft`·`card_evidence`·`check_result` 저장 | 근거 없음·충돌·검사 실패면 위 기준에 따라 초안 없이 사람에게 넘김 |
| 사람 카드·알림 | 감독 AI | `create_card`, `notify_staff`, `GET /cards/{card_id}` | `request_type`, `topic_key`, `summary`, `urgency`, `escalate_to_director=false` → `card_id`; `card_id`, `reason` → `notification_id` | 담당 담임, 담당이 없으면 미배정 | 요청 `awaiting_review`, 카드 `pending`(담당이 없으면 `unassigned`), `cards.due_at` 저장 | 저장 실패는 6.3을, 알림 실패는 5.4의 `notify_failed` 규칙을 따름 |
| 승인·회신 | 담임 | `POST /cards/{card_id}/decisions`, `GET /requests/{request_id}` | `version`, `decision=approve` 또는 `edit_approve`, `edited_content` → 카드·요청 상태, 학부모 회신 | 담임이 승인한 뒤 발송(5.3 ④) | 요청 `approved → sent_or_booked`, 카드 `approved → done`, `approvals (card_id, card_version)` 유니크 | 409 `CARD_VERSION_CONFLICT`·`ALREADY_DECIDED`. 본문 없이 승인하면 409 `INVALID_TRANSITION` |

**상담 예약**


| 단계 | 누가 | API·도구 | 입력 → 출력 | 권한(누가 할 수 있나) | DB 상태 변화(`requests.status`·`cards.status`·제약) | 실패하면 |
| --- | --- | --- | --- | --- | --- | --- |
| 접수·후보 | 학부모·감독 AI·코드 | `POST /requests`, `route_request`, `find_consult_slots` | `type=consultation`, `body`, `child_id` 등 → 요청; `teacher_id`, `date` → `slots[]`(최대 3개) | 본인 아이·담임 일정, 기관·반은 서버가 확인 | 요청 `received → classified → assigned → needs_info`, `consult_slots` 카드 `pending`, 후보 `proposed` | 후보 조회가 실패하면 1번 다시 부르고, 그래도 실패하면 시간을 지어내지 않음(5.4) |
| 가능한 시간 체크 | 학부모·감독 AI | `POST /requests/{request_id}/slot-choices`; 대화에서는 `request_consultation` | 화면 `slot_ids[]`; 도구 `teacher_id`, `date`, `time`, `topic?` → `slots[]`, 요청 상태 | 요청한 학부모만. 예약을 확정할 권한은 없음 | 후보 `chosen_by_parent` + `chosen_at`, 요청 `awaiting_review`, 카드 `pending` 유지 | 맞는 시간이 없으면 `none_fit` + `preferred_times`의 겹침·거리 순으로 후보를 다시 계산하고 담임에게 `parent_message`. 고른 후보는 24시간이 지나면 `proposed`로 풀림 |
| 담임 확정 | 담임·코드 | `POST /cards/{card_id}/bookings`, `book_slot` | `version`, `slot_id`; 도구 `slot_id`, `confirmed_by` → `booking_id`, API `booking { id, room, period }` | 카드 담당 교사만(다른 반 재배정 포함). 원장은 대신 확정하지 못함 | `approvals` 저장 후 요청 `approved → sent_or_booked`, 카드 `done`, 예약과 선택된 후보 `confirmed`. 요청당 확정 예약은 하나, 상담실과 담임 시간이 겹치지 않게 하는 배제 제약 | 409 `SLOT_NOT_CHOSEN`·`SLOT_TAKEN`·`CARD_VERSION_CONFLICT`. 확정 충돌은 해당 후보만 폐기하고 재제안·요청 needs_info·학부모 알림·slot_conflict_reproposed 저장 후 409 |

**긴급 민원 사람 인계**

| 단계 | 누가 | API·도구 | 입력 → 출력 | 권한(누가 할 수 있나) | DB 상태 변화(`requests.status`·`cards.status`·제약) | 실패하면 |
| --- | --- | --- | --- | --- | --- | --- |
| 분류·카드 두 장 | 학부모·감독 AI | `POST /requests`, `route_request`, `create_card` | `type=complaint` → `risk_level=urgent`, `risk_category`; `escalate_to_director=true` → `card_id` | 학부모 본인 아이. 위험 등급은 감독 AI가 분류한 뒤 사람이 판단 | 요청 `received → classified → assigned → escalated`, 초안 없는 `reply_draft` + `director_report` 카드 `pending`, 원장 보고 카드는 담당자 필수 | 분류·저장이 실패하면 재시도한 뒤 사람에게 인계(5.4·6.3). 자동 회신 없음 |
| 알림·상세 | 감독 AI·교직원 | `notify_staff`, `GET /cards`, `GET /cards/{card_id}` | `card_id`, `reason` → `notification_id`; 상세 `warnings[]`·`timeline[]` | 담임은 우리 반, 원장은 원 전체 | 요청 `escalated` 유지, 알림 `dedupe_key` 유니크·`deliver_after`(6.6) | 알림이 실패해도 카드는 유지. 긴급·판단 필요 카드에 `notify_failed`를 붙이고 실패 이력을 남김 |
| 사람 지시·재분류 | 원장·담임 | `POST /cards/{card_id}/instructions`, `POST /cards/{card_id}/reclassify` | 지시 `version`, `instruction` → 상태; 재분류 `version`, `risk_level`, `risk_category`, `reason` → 요청 | 지시는 원장만, 다시 분류는 담임·원장(원장 보고 카드는 원장만) | 지시: `approvals.decision=instruct`, 원장 카드 `done`, 요청 `awaiting_review`. 판단 필요 민원도 같은 인계 경로를 따르고, 긴급으로 재분류하면 `escalated` | 403 `FORBIDDEN_ROLE`, 409 `INVALID_TRANSITION`·`CARD_VERSION_CONFLICT` |
| 직접 작성·승인 | 담임 | `POST /cards/{card_id}/decisions` | `version`, `decision=edit_approve`, `edited_content.text` → 회신 | 원장이 지시한 뒤에도 담임의 승인 기록이 필요 | 요청 `approved → sent_or_booked`, 회신 카드 `done` | 초안도 직접 쓴 본문도 없거나 판단 필요 상태가 남아 있으면 409 `INVALID_TRANSITION` |

**도구 이름 대조.** 5.4의 도구 15개 가운데 `search_documents`·`find_consult_slots`·`request_consultation`·`get_my_requests`·`create_card` 5개는 30문항 2장과 이름이 같다. 나머지 10개는 30문항에 나오지 않아 대조할 대상이 없다. T12 화면 지도는 도구 이름 대신 화면과 API 필드로 적혀 있으므로, 세 문서의 이름이 모두 같다고 판정할 수는 없다. T12 화면과 API가 어떻게 이어지는지는 6.7에서 대조한다.

## 6. 실행 규칙

### 6.1 타임아웃

| 대상 | 기준 | 넘으면 |
| --- | --- | --- |
| API 응답(조회·결정·접수) | 10초 | 503 `UPSTREAM_UNAVAILABLE` 또는 500. AI 처리는 202로 떼어 내므로 이 시간에 들지 않음 |
| 모델 호출 1번 | 30초 | 재시도 대상(6.2) |
| 도구 호출 1번 | 30초(외부 법령·기상 API는 그 안에서 10초) | `TOOL_TIMEOUT`(`retryable` 참) |
| 요청 하나의 AI 처리 전체(2~5단계) | 3분 | 처리를 멈추고 초안 없는 카드로 사람에게 넘김. 넘긴 이유(`ai_timeout`)는 이력 `events.detail.handoff_reason`에 남김 |
| SSE 연결 | 처리 끝(`done`·`error`) 또는 5분 | 서버가 연결을 닫음. 화면은 상세를 다시 불러와 상태를 맞춤 |

요청 하나에 주어진 3분은 그래프 바깥의 실행기가 잰다. 분류, 공공 자료 가져오기, 답변 초안 쓰기와 검사는 모두 요청 행 잠금 밖에서 하고, 모델 응답을 기다리는 동안에는 DB 연결도 잡지 않는다. 잠금은 마지막 저장 때만 건다. 짧은 트랜잭션 안에서 요청 행을 잠근 뒤, 요청이 아직 처리 중인지 다시 확인하고 저장한다. 3분이 지나면 실행기는 더 기다리지 않고 코드 규칙으로 주제·긴급도·위험 등급·종류를 다시 저장한 뒤 유효한 담임에게 초안 없는 회신 카드(`pending`)를 배정한다. 일반이면 요청 `awaiting_review`와 담임 `new_card` 알림, 긴급·판단 필요면 원장 보고 카드와 요청 `escalated`, 담임·원장 위험 알림(`urgent_complaint`·`uncertain_complaint`)을 남긴다. 유효한 담임이 없는 반에서만 회신 카드를 `unassigned`로 두며, 일반 건의 `new_card` 알림은 원장에게 보낸다. 위험 카드 기한과 알림 시각은 정상 고위험 경로의 2시간·6.6 규칙을 그대로 따른다. 상담은 다르게 넘긴다. 시간 후보는 코드가 계산하므로 회신 카드 대신 시간 후보 카드(`consult_slots`)를 만들고 요청은 `needs_info`가 된다. 위험 상담이면 원장 보고 카드만 더하고 요청 상태는 담임 흐름 그대로 둔다(정상 경로와 같음). 후보 계산까지 실패할 때만 글로 답하는 회신 카드로 넘긴다. 3분이 되기 전에 처리가 예외로 멈췄다면 넘긴 이유를 `ai_failed`로 남긴다. 3분 뒤에 늦게 끝난 결과는 저장 직전 재확인 때 요청이 이미 사람에게 넘어가 있으므로 버려진다. 그래서 늦은 결과가 먼저 만든 카드를 덮지 못한다.

### 6.2 재시도

| 대상 | 다시 하는 것 | 다시 하지 않는 것 | 횟수·간격 |
| --- | --- | --- | --- |
| 모델 호출 | 타임아웃·429·5xx | 400·401·403·422(요청 자체가 잘못됨) | 최대 2번, 1초 → 2초(지수 백오프) |
| 도구 호출 | `retryable = true` | `retryable = false` | 1번 |
| 알림 발송 | 발송 실패 | 받는 사람 없음 | 최대 3번(`notifications.attempts`, FR-12) |
| 화면의 결정·확정 | 응답이 끊김 | 4xx | 카드·요청 상세에서 상태를 먼저 확인하고, 같은 `version`으로 1번 다시 보냄. 이미 처리됐으면 409 `ALREADY_DECIDED`로 막힘 |

### 6.3 202로 접수하는 작업의 상태 조회

202는 "접수했지만 처리는 아직 끝나지 않았다"는 뜻이다. 아래 세 작업은 모두 진행·성공·실패 상태를 조회할 수 있다. 작업이 실패해도 조회 요청 자체는 성공했으므로 응답은 200이고, 실패 여부는 상태 값으로 알린다.

| 접수 API | 조회 | 진행 중 | 성공 | 실패 |
| --- | --- | --- | --- | --- |
| 요청 만들기 | `GET /requests/{id}` + 스트림 | `received`·`classified`·`assigned` | `needs_info`(학부모 차례) 또는 `awaiting_review`(카드 생김) | 재시도 뒤에도 실패하면 코드 위험·분류와 유효한 담임 배정을 저장하고 초안 없는 카드로 사람에게 넘김. 일반은 `awaiting_review`·담임 `new_card`, 긴급·판단 필요는 `escalated`·원장 보고·담임과 원장 위험 알림. 유효한 담임이 없을 때만 미배정. 넘긴 이유(`ai_failed`)는 이력 `events.detail.handoff_reason`에 남기고, 교직원 스트림에는 `error` 이벤트를 보냄. 요청은 버리지 않음 |
| 알림장 초안 | `GET /daily-notes/drafts/{input_id}` | `draft_status = queued·running` | `succeeded`. 아이별 초안은 `GET /daily-notes?classroom_id=&date=`로 받음 | `failed` + `error { code, message }`(자세한 이유는 `events`의 `tool_failed`) |
| 자료 올리기 | `GET /documents/{document_id}` | `ingest_status = queued·running` | `succeeded` + `chunk_count`(조각 수). 충돌이 있으면 `status = conflict_pending` + `conflicts[]` | `failed` + `error { code, message }` |

**보류·상담 체크 주기 점검.** DB 워커 Beat는 1분마다 보류 예정일과 상담 체크 24시간 만료를 점검한다. 조회와 같은 _expire 경로를 쓰며 advisory lock·요청 잠금으로 이력과 알림을 한 번만 남긴다. 잠긴 요청은 다음 점검에서 처리한다. 미래 보류와 보류·원장 보고 중인 상담 체크는 보존하고, 상담 director_report 자동 재개는 보고 카드만 pending으로 바꾼다.

**보고 사유.** 새 escalated 이력의 detail.reason은 위험 분류·장애 인계면 risk, 같은 주제 민원 세 번째부터의 반복 보고면 repeat, 사람의 올리기·긴급 재분류면 manual이다. 위험과 반복이 겹치면 risk가 먼저다.

**카드가 끝내 안 생긴 요청.** 요청은 `POST /requests`에서 먼저 저장된다. 그래서 AI가 카드 만들기(`create_card`)까지 실패하거나 처리 중에 멈춰도 요청은 남는다. 서버 점검 작업은 5분마다 돌면서, 진행 중 상태(`received`·`classified`·`assigned`)인데 5분 넘게 카드가 없는 요청을 찾는다. 처음 찾았을 때는 처리를 한 번 다시 넣고 `agent_requeued` 이력만 남긴다. 다시 넣고 5분이 지나도 카드가 없으면, 코드 규칙으로 위험·분류를 다시 저장하고 정상 경로와 같은 유효한 담임 배정을 적용해 초안 없는 회신 카드를 만든다. 일반은 `awaiting_review`·담임 `new_card` 알림, 긴급·판단 필요는 원장 보고 카드·`escalated`와 담임·원장 위험 알림을 남긴다. 유효한 담임이 없을 때만 회신 카드가 미배정이고, 일반 건의 알림은 원장에게 보낸다. 이때 넘긴 이유 `card_missing`을 이력 `events.detail.handoff_reason`에 남긴다. 그동안 학부모 화면은 `received`·`classified`면 '접수됨', 담당 배정 뒤 `assigned`면 '선생님께 전달됨'으로 보인다. 인계 뒤 일반 건에 담당이 있으면 '선생님 확인 중', 담당이 없으면 '담당 선생님 배정 중'이고, 고위험 건은 '원장님 확인 중'이다. 채팅 안내는 '받았지만 선생님 확인이 늦어질 수 있음'으로 맞출 예정이지만, 이 문장은 아직 코드에 없다. DB 모드에서 RUN_IN=worker는 Beat가 5분마다 누락 카드 점검을 실행한다. RUN_IN=api는 API 시작 때 한 번, 이후 5분마다 별도 스레드에서 보류·상담 체크 만료와 누락 카드를 점검한다. API 프로세스 사이에는 advisory lock을 얻은 실행만 점검하며, 종료 때 주기 작업을 취소한다. 모의 API는 기존 조회 때 같은 만료 규칙을 적용한다. 두 모드를 나란히 비교한 결과는 6.7 마지막 사례에 있다.


```json
{ "input_id": "00000000-0000-4000-8000-000000000a01", "draft_status": "failed",
  "error": { "code": "UPSTREAM_UNAVAILABLE", "message": "모델 응답이 없어 초안을 만들지 못했어요." } }
```

### 6.4 중복·동시 실행 방지

| 상황 | 막는 것 | 결과 |
| --- | --- | --- |
| 같은 요청을 두 번 제출 | `requests (requester_id, client_request_id)` 유니크 | 200 + 처음 만든 요청 |
| 두 사람이 같은 카드를 동시에 결정 | 카드 `version` 비교 + `approvals (card_id, card_version)` 유니크 | 늦은 쪽은 409 `CARD_VERSION_CONFLICT`·`ALREADY_DECIDED` |
| 같은 시간에 상담 두 건을 확정 | 상담실·담임 시간 배제 제약, 요청당 확정 예약 하나 | 늦은 쪽은 409 `SLOT_TAKEN` |
| 같은 알림을 두 번 만듦 | `notifications.dedupe_key` 유니크 | 한 번만 저장·발송 |
| 같은 규칙을 두 번 제안 | `memory_rules` 부분 유니크 | 기존 `rule_id` |
| 반 알림장을 두 사람이 동시에 보냄 | 한 트랜잭션에서 반 단위로 잠금 | 먼저 보낸 쪽만 발송, 늦은 쪽은 `sent_count = 0` |

### 6.5 처리 기한(`due_at`) 계산

서버가 카드를 만들 때 계산해 `cards.due_at`에 넣는다. 계산은 요청 접수 시각에서 시작한다.

1. 문의·상담·민원의 긴급·판단 필요(2시간)는 접수 시각에 2시간을 그대로 더한다. 주말·공휴일에도 센다.
2. 그 밖의 기한(민원 일반·상담 24시간, 문의 4시간)은 시간을 더해 가다가 토요일·일요일·공휴일에 걸리면 그날을 통째로 건너뛴다.
3. 알림장 묶음은 그날 17:00, 원장 보고는 원래 요청 카드와 같은 기한이다. 정보 요청·규칙 제안은 기한이 없다(`NULL`).

| 접수 | 기한 종류 | `due_at` |
| --- | --- | --- |
| 화 10:00 | 문의 4시간 | 화 14:00 |
| 금 18:00 | 민원 일반 24시간 | 월 18:00 (금 6시간 + 토·일 건너뜀 + 월 18시간) |
| 토 10:00 | 상담 24시간 | 화 00:00 (토·일 건너뜀 → 월 00:00부터 24시간) |
| 금 23:00 | 민원 긴급 2시간 | 토 01:00 |


공휴일 목록은 MVP에서는 서버 설정(`.env`의 `HOLIDAYS`)으로 관리한다(8장). 기한과 알림은 같은 서버 설정(`HOLIDAYS`·`WORK_HOURS`)을 기준으로 삼지만 쓰는 방식이 다르다. 일반 기한은 평일이면 밤 시간도 세고, `WORK_HOURS`로 자르지 않는다. 근무 시간은 교직원 알림을 미룰 때만 쓴다. 긴급·판단 필요 2시간은 공휴일에도 그대로 센다.

### 6.6 알림 발송 시각(`deliver_after`)

이 값은 서버가 알림을 만들 때 계산해 `notifications.deliver_after`에 넣는다. 발송기는 `status = 'pending' AND deliver_after <= now()`인 알림만 꺼낸다. 아래 표는 8장의 기본 설정을 쓸 때의 값이다.

개인 알림 설정(API 64·65)이 있는 교직원은 하루 중 시간대만 3.36의 조용한 시간 규칙으로 바꾸고, 주말·HOLIDAYS에는 다음 근무일의 quiet_end까지 보류한다. 아래 기본 설정 예시는 개인 설정이 없을 때 적용한다.

| 받는 사람 · 알림 | 근무 시간(평일 09:00~18:00, 공휴일 제외) 안 | 근무 시간 밖 |
| --- | --- | --- |
| 교직원 · 긴급 요청(문의·상담·민원) 중 아이 안전(`risk_category = child_safety`) | 바로 | 바로 |
| 교직원 · 그 밖의 긴급 요청(교직원 위협·법적 조치·개인정보)과 판단 필요 요청 | 바로 | 다음 근무 시작(09:00) |
| 교직원 · 그 밖의 알림(새 카드·보류 재개·잡아 둔 시간 풀림 등) | 바로 | 다음 근무 시작(09:00) |
| 학부모 · 모든 알림 | 바로 | 바로 |

근무 시간 밖 규칙은 교직원이 받는 알림에만 쓴다(FR-21: 퇴근 뒤 알림은 모아 두고 아이 안전·발열만 바로 보냄). 학부모 알림은 학부모가 보낸 요청이 어떻게 진행되는지 알리는 소식이므로, 시간과 상관없이 바로 보낸다. 발열 같은 건강 알림은 아직 이 표에 없으며 투약·귀가(T46)에서 더한다. 근무 시간과 바로 보낼 위험 종류도 MVP에서는 서버 설정(`.env`의 `WORK_HOURS`·`IMMEDIATE_RISK_CATEGORIES`)으로 관리한다(8장). 근무일은 기한 계산과 같은 `HOLIDAYS`로 고르고, 근무 시간은 `WORK_HOURS`의 시작 이상·끝 미만으로 본다. 위험 종류 설정은 긴급 요청일 때만 적용한다.

#### 6.6.1 공휴일·퇴근 뒤 알림과 지연 예시

아래 표의 값은 `schedule.py`로 계산했다. 시간대는 모두 한국 표준시(+09:00)이고, 설정은 `HOLIDAYS=2026-12-25`, `WORK_HOURS=09:00-18:00`, `IMMEDIATE_RISK_CATEGORIES=child_safety`다. 2026년 12/25(금)이 공휴일이어서, 공휴일 전날(12/24 목) 뒤로 공휴일과 주말까지 사흘을 건너뛰는 경우도 함께 넣었다. 학부모 열은 그 접수 시각에 보낼 알림이 생겼다고 가정하고 계산한 값이다. 실제로 이 표의 민원은 접수만으로는 학부모 답변이나 알림을 만들지 않으며, 회신 알림은 승인·발송 시각에 다시 계산한다.

| 상황 | 접수 시각 | 요청 종류·위험 | 교직원 알림 `deliver_after` | 학부모 알림 | 처리 기한 `due_at` | 지연 표시가 켜지는 시각(`is_delayed = due_at < now()`) |
| --- | --- | --- | --- | --- | --- | --- |
| 금요일 퇴근 뒤 | 2026-12-18 금 18:30 | 민원 일반(`complaint`, `normal`) | 12/21 월 09:00 | 발생 즉시(가정: 12/18 18:30) | 12/21 월 18:30 | 12/21 18:30 초과부터 |
| 공휴일 전날 근무 중 | 2026-12-24 목 17:30 | 민원 일반(`complaint`, `normal`) | 12/24 목 17:30 | 발생 즉시(가정: 12/24 17:30) | 12/28 월 17:30 | 12/28 17:30 초과부터 |
| 공휴일 전날 퇴근 뒤 | 2026-12-24 목 18:30 | 민원 일반(`complaint`, `normal`) | 12/28 월 09:00 | 발생 즉시(가정: 12/24 18:30) | 12/28 월 18:30 | 12/28 18:30 초과부터 |
| 아이 안전 긴급, 근무 밖 | 2026-12-18 금 20:00 | 민원 긴급(`urgent`, `child_safety`) | 12/18 금 20:00 | 발생 즉시(가정: 12/18 20:00) | 12/18 금 22:00 | 12/18 22:00 초과부터 |
| 교직원 위협 긴급, 근무 밖 | 2026-12-18 금 20:00 | 민원 긴급(`urgent`, `staff_attack`) | 12/21 월 09:00 | 발생 즉시(가정: 12/18 20:00) | 12/18 금 22:00 | 12/18 22:00 초과부터 |

현재 시각이 기한과 같을 때는 아직 지연이 아니다. 마지막 사례에서는 교직원 알림이 오기 전에 지연 표시가 먼저 켜진다. 긴급 2시간 기한과 교직원 알림 예외가 서로 다른 규칙이어서 생기는 일이다. 표의 다섯 행과 기한 경계(같은 시각·1마이크로초 뒤)는 `test_documented_holiday_notification_examples`가 고정한다.

#### 6.6.2 상담 종료·지연 알림

Beat는 1분마다 시작이 하루 이내인 확정 예약을 읽고, 그중 실제로 알림을 넣을 예약만 잠근다. 종료 알림 `consultation_ending`은 지금이 시작 이후이면서 예상 종료 10분 전 이상·종료 미만일 때 담임에게 남긴다. 지연 시각이 없으면 원래 종료 시각을 기준으로 삼는다. 상담 중인 담임에게 주는 안내이므로 근무 시간 밖에도 바로 만들고 보낸다. Beat 주기가 늦어지면 종료 전까지만 밀린 알림을 따라잡고, 종료 뒤에는 지난 알림을 만들지 않는다.


지연은 시간이 흐른 것만 보고 추측하지 않는다. 3.28의 HTTP API로 담임의 예상 종료를 기록하고, 같은 트랜잭션에서 `consultation_delay_reported` 이력을 남긴다. 상담 완료나 취소는 지연 신호로 보지 않는다. 앞 상담이 이미 시작됐는데 명시적으로 기록된 예상 종료가 뒤 예약의 시작보다 늦으면, 뒤 예약의 담임과 신청 학부모에게 `consultation_delayed`를 남긴다. 여기서 뒤 예약은 같은 기관에서 같은 담임이나 같은 상담실을 쓰는 예약이다. 이 알림에 앞 상담의 학부모·아이 정보는 넣지 않는다. 대체 시간은 예상 종료 뒤 14일 안에서 최대 세 개를 제안한다. 후보를 고를 때는 근무일·근무 시간, 활성 상담실, 담임 일정, 확정 예약의 연장 구간, 살아 있는 학부모 체크, 승인된 시간 규칙을 모두 적용한다. 빈 시간이 없으면 다른 날짜를 안내한다. 제안만으로는 예약이나 학부모 체크가 바뀌지 않으며, 예약 변경·취소는 3.28의 후속 계약에서 다룬다.

알림을 구분하는 키는 예약, 알림 종류, 기준 시각, 수신자로 만든다. 기준 시각은 종료 알림이면 종료 예정 시각, 대체 시간 알림이면 지연이 끝나는 시각(until)이다. 그래서 같은 값으로 다시 실행해도 중복 알림이 생기지 않는다. 지연 값이 바뀌면 새 종료 알림과 대체 시간을 다시 계산한다. 이때 옛 pending 알림은 held로 돌리고, 이미 보낸 알림은 그대로 보존한다. 옛 제안에 대해서는 `consultation_reminded` 이력에 `outcome=superseded`와 알림 ID를 한 번 남기고, 새로 만든 알림의 생성 이력에는 until과 제안 시각을 남긴다. 지연 값이 그대로인 채 상담이 끝나면 superseded 이력은 남기지 않는다.

대체 시간 알림에는 기존 교직원 근무 시간 규칙을 그대로 적용한다. 그 규칙에 따라 미룬 시각이 예약 종료 이상이면 그 알림은 만들지 않는다. 발송하거나 재시도할 때 예약이 종료·완료·취소됐거나 알림이 현재 지연 값과 어긋나면, 그 알림은 held로 남긴다. **발송 기록만 held, 목록 노출은 유지**한다. 목록은 원래 deliver_after를 기준으로 보여 준다. 이 점검은 DB 워커에서 주기적으로 실행하고, mock에서는 HTTP 입력 직후에 같은 점검을 실행한다.

### 6.7 대표 사례 대조 — 화면·API·DB가 같은 상태로 보이는지

화면 ID와 표시 이름은 T12 화면 지도를 따르고, API 경로에서는 `/api/v1`을 생략했다. DB 제약은 DB 스키마 설계서(T09)를 기준으로 적었다. 아래 시험은 2026-11-20에 메모리 모의 API로 돌린 결과이고, 실제 DB 제약을 확인하는 시험은 DB 설계서 9.1에 따로 있다. 실행 환경과 전체 결과, 문서와의 차이는 [T13 시험 기록](T13_시험기록_2026-11-20.md)에 있고, 시험 함수는 `tests/integration/api/test_flows.py`에 있다.

**상담 예약 중복 방지**

| 단계 | 화면(T12의 화면 ID·표시 이름) | API | DB(상태·제약) | 권한 | 시험(테스트 함수 이름) |
| --- | --- | --- | --- | --- | --- |
| 후보·체크 | P-04 요청 상세: 시간 체크 → 선생님 확인 중, T-02 카드 상세: 시간 확정 | `GET /requests/{request_id}`, `POST /requests/{request_id}/slot-choices` | 요청 `needs_info → awaiting_review`, 후보 `proposed → chosen_by_parent`, 카드 `pending` | 요청한 학부모만 체크 | `test_consultation_complete_booking_flow` |
| 담임 확정 | T-02 카드 상세: 확정, P-04 요청 상세: 예약 확정 | `POST /cards/{card_id}/bookings`, `version`·`slot_id` → `booking` | 요청 `approved → sent_or_booked`, 카드 `done`, 예약 `confirmed`, `approvals (card_id, card_version)` 유니크 | 그 반 담임만, 원장은 403 `FORBIDDEN_ROLE` | `test_consultation_complete_booking_flow` |
| 같은 시간 충돌 | T-02 카드 상세: 방금 다른 예약이 들어왔어요 · 후보를 다시 만들어요 | 같은 확정 API → 409 `SLOT_TAKEN` | 상담실·담임의 시간 배제 제약, 요청당 `confirmed` 예약 하나. 실패한 카드·후보는 상태 유지 | 담임, 같은 범위 재검사 | `test_slot_collision_is_atomic_and_nonoverlap_is_allowed`(순차 충돌). 동시 예약 경합 시험 없음 |

**민원 처리 완료 — 학부모 확인 있음·없음**

| 단계 | 화면(T12의 화면 ID·표시 이름) | API | DB(상태·제약) | 권한 | 시험(테스트 함수 이름) |
| --- | --- | --- | --- | --- | --- |
| 회신·확인 | P-04 요청 상세: 답변 도착 → 확인함 · 선생님이 마무리하고 있어요, T-01 받은함: 확인 필요(처리 완료 대기) | 결정 `approve` 후 `POST /requests/{request_id}/confirm` | 요청 `sent_or_booked` 유지, `requests.parent_confirmed_at` 기록, 알림 `dedupe_key` 유니크 | 담임이 승인, 요청한 학부모만 확인 | `test_complaint_approval_confirmation_completion` |
| 확인한 민원 완료 | T-02 카드 상세: 처리 완료, P-04 요청 상세: 완료 | `POST /cards/{card_id}/decisions`, `decision=complete`, `version=2` → `completed` | `approvals.decision=complete`, 요청 `completed`, 카드 `done` | 담임. 회신 전이면 409 `INVALID_TRANSITION` | `test_complaint_approval_confirmation_completion` |
| 미확인 민원 완료 | T-02 카드 상세: 학부모 확인 기다리는 중·처리 완료, 이유 글 필수 | 같은 결정 API, `reason_text` 필수. 없으면 409 `REASON_REQUIRED` | `parent_confirmed_at IS NULL`, `approvals.reason_text` 저장 후 `completed`, 카드 `done`. 트리거 `approvals_unconfirmed_complete_reason` | 담임이 이유를 남김 | `test_unconfirmed_complete_needs_reason_and_overview_counts` |
| 미확인 완료 구분 | D-03 원 현황: 학부모 미확인 완료(`completed_unconfirmed`), 남긴 이유 함께 표시(T53) | `GET /overview` → `completed_unconfirmed` | `director_overview.completed_unconfirmed`: 최근 30일의 미확인 완료 민원을 요청별로 셈. 이유는 `approvals.reason_text` | 원장만, 담임은 403 `FORBIDDEN_ROLE` | `test_unconfirmed_complete_needs_reason_and_overview_counts`(건수·권한). 화면 이유 표시 시험 없음 |

**긴급 민원 사람 인계**

| 단계 | 화면(T12의 화면 ID·표시 이름) | API | DB(상태·제약) | 권한 | 시험(테스트 함수 이름) |
| --- | --- | --- | --- | --- | --- |
| 초안 없이 인계 | T-01 받은함: 긴급·확인 필요, T-02 카드 상세: AI 초안 없음, D-01 받은함: 원장 보고 | `POST /requests`, 카드 목록·상세 조회 | 요청 `escalated`, `reply_draft`·`director_report` 카드 `pending`, 위험 종류·원장 보고 담당 필수 | 담임은 우리 반, 원장은 원 전체 | `test_director_report_permission_instructions_reassign`(카드·권한). 초안 없음·승인 전 학부모 답 없음 전용 시험 없음 |
| 원장 지시 | D-02 카드 상세: 지시 남기기, T-02 카드 상세: 확인 필요 | `POST /cards/{card_id}/instructions`, `instruction`·`version` | `approvals.decision=instruct`, `reason_text`=지시, 원장 카드 `done`, 요청 `awaiting_review`, 이력 `instructed` | 원장만. 담임이 원장 보고 카드를 결정·지시하면 403 `FORBIDDEN_ROLE` | `test_director_report_permission_instructions_reassign` |
| 판단 필요 재분류 | T-02 카드 상세: 다시 분류 일반/긴급 → 확인 필요 또는 원장 보고 | `POST /cards/{card_id}/reclassify`, `risk_level`·`risk_category`·`reason`·`version` | 요청 `awaiting_review`, 긴급이면 다시 `escalated`, 보고 카드는 중복 생성 안 함 | 담임·원장, 원장 보고 카드는 원장만 | `test_reclassify_uncertain_and_escalate` |
| 사람이 쓴 답 승인 | T-02 카드 상세: 직접 답 쓰기 → 승인하고 보내기, P-04 요청 상세: 답변 도착 | `POST /cards/{card_id}/decisions`, `decision=edit_approve`, `edited_content.text` | 승인 기록 뒤 요청 `sent_or_booked`, 회신 카드 `done` | 담임 승인(5.3 ④) | `test_explicit_escalation_and_edit_approval`(일반 민원의 수동 인계). 긴급 민원 회신까지 연결한 시험 없음 |

**요청은 접수됐지만 인계 카드 저장에 실패**

학부모에게 접수와 담당 배정을 구분해 보인다. 실행 기준은 2.2다. 모의 모드의 정상 카드 생성과 담당 없는 반은 공용 HTTP 시험으로 확인하고, 카드 저장 장애 주입은 시험 PG에서만 확인한다.

| 시점 | 학부모 `status_label` | 모의·시험 PG에서 확인하는 것 |
| --- | --- | --- |
| 접수 직후, 실행 전 | 접수됨 | `received`, 담당·카드 없음(`test_received_request_label_before_agent_runs`) |
| 분류 뒤 | 접수됨 | `classified`, 문구 단위 표 |
| 담임 배정 뒤 | 선생님께 전달됨 | `assigned`, 문구 단위 표 |
| 담임 있는 반의 일반 카드 저장 장애 인계 | 선생님 확인 중 | 요청 `awaiting_review`, 담임 회신 카드 `pending`·초안 없음, 담임 `new_card` 알림(`db/test_requests.py::test_agent_failure_preserves_request_and_hands_off_without_private_error`) |
| 유효한 담임 없는 반의 카드 생성 / 장애 인계 | 담당 선생님 배정 중 | 요청 `awaiting_review`, 회신 카드 `unassigned`, 요청 담당 없음·원장 `new_card` 알림. 일반 건의 정상·장애 경로 모두 같음 |
| 고위험 카드 저장 장애 인계 | 원장님 확인 중 | 코드 위험·분류 저장, 초안 없는 담임 회신 카드·원장 보고 카드, 요청 `escalated`, 담임·원장 위험 알림(`db/test_requests.py::test_handoff_keeps_code_risk_assignment_and_notifications`) |
| 카드가 끝내 없고 점검에서 다시 넣음 | 현재 상태에 따른 표시 유지 | `agent_requeued`만으로 담임 전달로 표시하지 않음 |
| 다시 넣어도 카드가 없어 사람에게 넘김 | 일반·담임 있음: 선생님 확인 중 / 없음: 담당 선생님 배정 중 / 고위험: 원장님 확인 중 | `card_missing`에도 같은 코드 위험·담임 배정·원장 보고 규칙 적용. 자동 복구 성공으로 세지 않음 |
| 원장이 담당 재배정 | 선생님 확인 중 | 담당 있음, 상태는 `awaiting_review` 그대로(`test_unassigned_request_label_changes_after_director_reassign`) |

### 6.8 장애 결과 구분

아래는 기존 장애 시험을 결과로 나눈 표다(2026-11-24, 이 PR HEAD, 0011; `tools/test_db.sh -p no:cacheprovider`, 단위 시험은 2.2 모의 전체 명령). 자동 복구는 재시도 뒤 검증한 결과가 준비된 경우에만 적는다. 카드만 생기거나 작업 상태만 `succeeded`가 된 것은 그 근거가 아니다. 알림장 아이별 집계 기준은 DB 2.6의 T58 규칙을 따른다.

| 기존 장애 시험 | 자동 복구 | 사람에게 넘김 | 이유·검증 |
| --- | --- | --- | --- |
| `unit/test_daily_note_graph.py::test_writer_retry_once_then_succeeds` | 재시도 뒤 확인 항목 없는 아이 초안 | — | `open_checks=[]`·메모 줄 있음. 저장·실제 모델 시험은 아님 |
| `db/test_worker_db.py::test_broker_failure_marks_note_failed_and_teacher_regenerates_while_request_sweep_recovers` | 요청 다시 등록 뒤 회신 카드·본문 저장 | — | `card_missing` 없음. 알림장 큐 실패는 `failed`·`queue_error`로 남고 담임 재생성으로 복구. `succeeded`만으로 T58 성공은 판정하지 않음 |
| `db/test_request_lock_timeout.py::test_ai_timeout_hands_off_empty_card_and_drops_late_draft` | — | 초안 없는 담임 카드 | `ai_timeout`; 위험·담임 보존, 늦은 초안이 덮지 못함 |
| `db/test_requests.py::test_agent_failure_preserves_request_and_hands_off_without_private_error` | — | 초안 없는 담임 카드(유효한 담임이 없을 때만 미배정) | `ai_failed`; 요청·코드 분류 보존, 담임 `new_card`(없으면 원장) |
| `db/test_worker_db.py::test_queued_request_is_republished_once_then_handed_off_after_five_more_minutes` | — | 재등록 뒤에도 카드가 없어 초안 없는 담임 카드 | `card_missing`; 위험·담임 보존 |
| `db/test_daily_note_recovery.py::test_failed_retry_is_handed_off_then_partial_template_is_fallback` | 검증·저장된 아이별 결과만 후보 | 작업 실패·템플릿 아이는 사람에게 넘김 | 기존 반 단위 집계의 `fallback`을 전체 성공으로 읽지 않음(DB 2.6) |

## 7. API 필드와 DB 컬럼 대응

'대응' 열에는 이름이 다른 곳만 적었다. ID 형식은 DB 설계서 2.0을 따르고, 3.7에 나온 화면용 칸의 대응은 그 표의 'DB' 열에 적었다.

| API 필드 | DB 컬럼 | 대응 |
| --- | --- | --- |
| `request.id` · `request_id`(경로) | `requests.id` | UUID |
| `client_request_id` | `requests.client_request_id` | 같음 |
| `type` · `body` · `child_id` · `previous_request_id` | `requests.type` · `body` · `child_id` · `previous_request_id` | 같음 |
| `request.status` | `requests.status` | 같음 |
| `request.status_label` | `requests.status`·`assignee_id` | 저장하지 않음. 역할·상태·담당 유무로 계산(3.2) |
| `request.missing_fields[]` | `requests.missing_fields` | `jsonb` 목록 |
| `request.parent_confirmed_at` | `requests.parent_confirmed_at` | 같음 |
| `request.hold_until` | `cards.hold_until` | 요청의 보류 카드에서 가져옴 |
| 반(요청) | `requests.classroom_id` | API로 받지 않고 `children.classroom_id`에서 채움 |
| `messages[]` | `request_messages` | `sender_type`·`body`·`created_at` |
| `messages[].sender_role` | `users.role` | `request_messages.sender_id`로 쓴 사람을 찾아 그 사람의 역할을 넣음. `sender_type`이 `user`가 아니면 null |
| `timeline[]` | `events` | `to_status`를 표시 이름으로 바꿈. 학부모용에는 상태 변화만 담음 |
| `card.version` · `version`(본문) | `cards.version` | 정수 |
| `decision` · `reason_code` · `reason_text` · `edited_content` | `approvals.decision` · `reason_code` · `reason_text` · `edited_content` | 같음. 본문 `version`은 `approvals.card_version`에 들어감 |
| `hold_until`(본문) | `cards.hold_until` | `date` |
| `risk_level` · `risk_category` · `topic_key` | `requests.risk_level` · `risk_category` · `topic_key` | 같음 |
| `repeat_count` | — | 저장하지 않음. 조회할 때 `requests_repeat_idx`로 셈 |
| `due_at` · `is_delayed` | `cards.due_at` | `is_delayed = due_at < now()` |
| `evidence[].document_title` · `location` · `effective_from` · `quote` | `documents.title` · `document_chunks.location` · `documents.effective_from` · `card_evidence.quote` | `card_evidence → document_chunks → documents` |
| `slots[].id` · `slot_ids[]` · `slot_id` | `consultation_slots.id` | 정수 |
| `slots[].period` · `booking.period` | `consultation_slots.period` · `consultation_bookings.period` | `tstzrange` ↔ `{ start, end }` |
| `booking.room` | `rooms.name` | `consultation_bookings.room_id`로 이어 방 이름을 줌 |
| `draft_status` · `input_id` | `daily_note_inputs.draft_status` · `id` | 같음 |
| 마지막 AI 초안(내부 저장) | `daily_notes.ai_original` | 0003. 교사가 고쳐도 원본은 바뀌지 않고, 교사가 고치지 않은 미확인 초안을 다시 만들 때 갱신함. 기존 행은 적용 시점의 content로 채움 |
| 알림장 상태 이력 | `events.daily_note_id` | 기관 복합 FK. daily_note_drafted·daily_note_edited·daily_note_confirmed·daily_note_sent |
| 내 기억 목록·삭제 | `memories` | owner_id가 본인이고 deleted_at이 비어 있는 행. 삭제하면 deleted_at에 표시함 |
| `child_memos[]` | `daily_note_inputs.child_memos` | 0002의 jsonb NOT NULL DEFAULT '[]'::jsonb, 배열 CHECK. 아이 UUID·중복·소속·메모 길이는 API가 검사함 |
| `notes[].status` · `content` · `open_checks[]` | `daily_notes.status` · `content` · `open_checks` | 같음 |
| `notes[].version` · `corrected_at` | `daily_notes.version` · `corrected_at` | 0015. 정정용 판·마지막 정정 시각, 학부모 응답에도 포함(3.30) |
| `ingest_status` | `documents.ingest_status` | 같음 |
| `chunk_count` | — | 저장하지 않음. 그 문서에 딸린 `document_chunks` 개수 |
| 넘긴 이유(`ai_timeout`·`ai_failed`·`card_missing`, 분류 결과의 `handoff_reason`) | `events.detail->>'handoff_reason'` | 칸을 따로 두지 않고 이력에 넣음 |
| `notification.kind` · `read_at` | `notifications.kind` · `read_at` | 같음 |
| `completed_unconfirmed` 등 원장 현황 숫자 | `director_overview` 뷰 | 뷰의 칸 이름 그대로 |
| 피드 글·사진·아이 표시·공개 범위 | `feed_posts` · `feed_photos` · `feed_photo_children` · `children.photo_scope` | 3.29. 사진 바이트는 파일로 두고, file_url은 인증 API 주소로 계산함 |
| `trace_id` · `X-Request-ID` | `events.detail->>'trace_id'` | 칸을 따로 두지 않고 이력 `detail`에 넣음 |

## 8. 설정값

MVP 설정값은 서버 설정(`.env`)으로 관리한다. `.env.example`에는 이름과 기본값만 두고, 비밀 값은 넣지 않는다.

공휴일은 모든 기관에 똑같고 1년에 한 번 바뀐다. 그래서 원장이 화면에서 이 설정을 고치는 기능은 MVP 범위 밖이다. 나중에 원장이 기관별 재량휴업일이나 근무 시간을 바꾸는 기능이 생기면, 그 설정을 DB의 기관 설정 테이블로 옮기고 그때 DB 스키마 설계서에도 더한다.

| 이름 | 기본값 | 뜻 |
| --- | --- | --- |
| `JWT_SECRET` | 개발용 기본 문자열(배포 때 반드시 바꿈) | 토큰 서명 키. 32바이트 이상 |
| `JWT_ACCESS_TTL_HOURS` | `12` | 토큰 수명 |
| `CORS_ORIGINS` | `http://localhost:5173` | 허용할 화면 출처. 쉼표로 구분해 여러 주소를 넣음 |
| `HOLIDAYS` | `""`(빈 문자열, 공휴일 목록 없음) | YYYY-MM-DD를 쉼표로 나열. 기한과 교직원 알림 시각에 적용 |
| `WORK_HOURS` | `09:00-18:00` | 교직원 근무 시간. HH:MM-HH:MM 형식이고, 같은 날 안에서 시작 < 끝. 시작 시각은 포함하고 끝 시각은 제외 |
| `IMMEDIATE_RISK_CATEGORIES` | `child_safety` | 근무 시간 밖에도 바로 보내는 긴급 위험 종류. child_safety·staff_attack·legal_external·privacy_leak 중에서 골라 쉼표로 나열 |
| `MEDIA_DIR` | `var/media` | 피드 파일을 저장하는 폴더(3.29). mock은 mock/만 초기화하고 DB 파일은 그대로 둠 |
| `MOCK_STREAM_DELAY_MS` | `300` | 모의 SSE 이벤트 사이의 간격(밀리초). 음수를 넣으면 0으로 처리 |
| `QA_TOOLS` | `false` | `true`·`1`만 참. 팀 QA 서버에서만 알림장 초기화·사람별 원 도구(3.39~3.40)를 켜고 운영에서는 금지 |
| `LLM_MODEL_DEFAULT` | `gpt-6-luna` | 역할별 모델 칸이 비어 있을 때 쓰는 모델 |
| `LLM_MODEL_SUPERVISOR` | (비움) | 감독 AI 모델 |
| `LLM_MODEL_DOCUMENT` | (비움) | 자료 AI 모델 |
| `LLM_MODEL_MEMORY` | (비움) | 기억 AI 모델 |
| `LLM_MODEL_CHECKER` | (비움) | 검사 AI 모델 |
| `LLM_MODEL_CODE` | (비움) | 코드 AI 모델 |
| `DAILY_NOTE_WRITER_TIMEOUT` | `300` | 초안 입구 함수가 기다리는 제한 시간(초). 넘기면 failed가 되고, 늦게 온 결과는 저장하지 않음 |
| `NOTE_DRAFT_CONCURRENCY` | `5` | 알림장 그래프의 `ThreadPoolExecutor`가 동시에 처리할 최대 아이 수. 최솟값 1이며, 1이면 순서대로 처리함(5.5.1) |
| `OPENAI_API_KEY` | (비움) | 모델 호출에 쓰는 키. 값은 팀이 키를 보관하는 곳에서 받음 |

역할별 모델 칸을 비워 두면 `LLM_MODEL_DEFAULT`를 쓴다. 역할별로 모델을 바꾸는 일은 다섯 에이전트 분리(T43) 뒤에 하며, 앱을 거친 평가에서 이득이 확인된 역할만 팀 결정으로 바꾼다.

공휴일·근무 시간·즉시 알림 위험 종류는 기동할 때 `load_settings()`가 읽는다. 이때 날짜·시각 형식이 틀렸거나, 종료 시각이 시작 시각과 같거나 앞서거나, 위험 종류 목록이 비었거나 허용되지 않은 위험 종류가 들어 있으면 `ValueError`를 내며 기동을 멈춘다. 6.5·6.6의 기한과 알림도 이 설정을 그대로 쓴다.

## 부록 A. 예시 ID

문서 예시, 계약표 부록 A, 팀 자체 30문항이 모두 같은 값을 쓰고, 시드(`db/seeds`)도 이 UUID로 만든다.

| 데모 이름 | 무엇 | 표 | 고정 UUID |
| --- | --- | --- | --- |
| `KG-DEMO-01` | 가상 햇살유치원 | `organizations` | `00000000-0000-4000-8000-000000000001` |
| `CL-DEMO-01` | 만 4세 별빛반 | `classrooms` | `00000000-0000-4000-8000-000000000101` |
| `CL-DEMO-02` | 만 5세 햇님반 | `classrooms` | `00000000-0000-4000-8000-000000000102` |
| `T-DEMO-01` | 우리 반 담임 | `users` | `00000000-0000-4000-8000-000000000201` |
| `T-DEMO-02` | 다른 반 교사(권한 거부 시험용) | `users` | `00000000-0000-4000-8000-000000000202` |
| `teacher03` | 맡은 반이 없는 보조 교사(재배정 시험용, 표시 이름 '보조 선생님') | `users` | `00000000-0000-4000-8000-000000000203` |
| `D-DEMO-01` | 원장 | `users` | `00000000-0000-4000-8000-000000000301` |
| `P-DEMO-01` | 우리 아이 학부모 | `users` | `00000000-0000-4000-8000-000000000401` |
| `P-DEMO-02` | 다른 아이 학부모 | `users` | `00000000-0000-4000-8000-000000000402` |
| `C-DEMO-01` | 우리 아이 | `children` | `00000000-0000-4000-8000-000000000501` |
| `C-DEMO-02` | 다른 아이(권한 거부 시험용) | `children` | `00000000-0000-4000-8000-000000000502` |
| `C-DEMO-03` | 별빛반 노을, 보호자 P-DEMO-02 | `children` | `00000000-0000-4000-8000-000000000503` |
| `RM-DEMO-01` | 상담실 | `rooms` | `00000000-0000-4000-8000-000000000601` |
| `R-DEMO-01` · `R-DEMO-02` | 상담 요청 · 민원 요청 | `requests` | `…000000000701` · `…000000000702` |
| `R-DEMO-08` · `R-DEMO-10` | 하늘 문의 "기침해요" · 노을 귀가 "오늘 할머니가 데리러 가요"(가상) | `requests` | `…000000000708` · `…00000000070a` |
| `K-DEMO-01` · `K-DEMO-02` | 상담 후보 카드 · 민원 회신 카드 | `cards` | `…000000000801` · `…000000000802` |

피드 글 `e01`~`e04`(반 2·원 2)는 `feed_posts`에서 `…000000000e01`~`…000000000e04`를 쓰고, 사진 `f01`~`f05`는 `feed_photos`에서 `…000000000f01`~`…000000000f05`를 쓴다(가상 아이 JPEG, 3.29).

별빛반(`…0101`, 만 4세, teacher01)은 하늘·노을에 `roster_c4.json` 명단의 18명을 더해 20명이다. 명단의 `C4-NN`은 `demo_id("54NN")`으로 바꿔 쓰며, 명단 아이에게는 보호자가 없다. 햇님반(`…0102`, 만 5세, teacher02)에는 바다 1명뿐이다. 반 이름, 교사 표시 이름, 아이 이름과 순서는 `apps/api/app/mock/seed.py`에 있다.


알림장에 연결하는 두 요청은 모의 저장소를 초기화하는 날짜에 접수 상태로 넣는다. 문의·귀가를 처리할 카드는 아직 만들지 않는다.

그 밖의 데모 요청(…703~707), 문서(…b01~b03), 규칙(…d01)은 `apps/api/app/mock/seed.py`를 참고한다.

## 부록 B. 강사 가이드 체크리스트 대조

| 체크리스트(가이드 33쪽) | 이 문서 |
| --- | --- |
| 구현할 API가 모두 목록 표에 있고 요구사항 ID와 연결된다 | 2장(77개, 요구사항 열·상태 칸) |
| 서버 주소·인증·오류 형식·/docs·변경 이력이 있다 | 1장, 끝의 변경 이력 |
| 구현할 API마다 상세 명세와 필드 명세 표가 있다 | 3장(77개 전부) |
| 형식 오류(422)와 권한·승인 오류(403)를 나눠 적었다 | 4.1 |
| 202를 쓰는 API는 작업 상태·결과·실패 조회가 있다 | 3.19.1, 6.3 |
| Tool마다 성공·실패 출력과 실패 후 처리가 있다 | 5.2, 5.4, 5.5, 5.7 |
| 타임아웃·재시도·중복 실행 방지 규칙이 있다 | 6.1, 6.2, 6.4, 6.7 |
| ID 형식이 같고, 필드와 DB 컬럼의 대응이 분명하다 | 1.5, 5.7, 6.7, 7장 |

## 변경 이력

| 판 | 날짜 | 내용 | 작성 |
| --- | --- | --- | --- |
| v0.1 | 2026-11-18 | 초안. API 목록 29개와 핵심 6개 상세 명세, 화면용 조회 칸, 검증·권한 규칙, 도구 실패 처리, 실행 규칙, 필드와 DB 컬럼 대응, 설정값을 적음 | 태웅 |
| v0.2 | 2026-11-18 | 나머지 API 상세 명세(3.8~3.23)를 모의 API·OpenAPI와 대조해 채움 | 태웅 |
| v0.3 | 2026-11-20 | 업무 흐름 세 개(5.7), 공휴일·퇴근 뒤 알림 예시(6.6.1), 대표 사례 대조(6.7), 교직원 알림이 실패했을 때의 경고, 원에 남은 답 예외를 더함 | 태웅 |
| v0.4 | 2026-11-20 | 알림장의 아이별 메모, 확인 항목 종류 8개, 반 아이 목록 API(30)를 더함 | 태웅 |
| v0.4.1 | 2026-11-20 | 알림장의 보호자 문의 줄(`inquiry`)과 초안 대기 제한·동시 실행 설정을 더함 | 태웅 |
| v0.5 | 2026-11-20 | 알림장의 AI 원본과 아이별 이력, 내 기억 보기·지우기(31·32), 알림장 다시 만들기(33)를 더함 | 태웅 |
| v0.5.1 | 2026-11-20 | 다시 만들 때 교사 수정본을 지키는 규칙과 이력 구분을 더함 | 태웅 |
| v0.5.2 | 2026-11-20 | 상담 시간 체크·확정 규칙(지난 시간·체크 충돌·보류 중 체크 유지·동시 확정 잠금)을 맞춤 | 태웅 |
| v0.5.3 | 2026-11-20 | 상담 종료 10분 전 알림과, 상담이 지연될 때의 대체 시간 알림(6.6.2)을 더함 | 태웅 |
| v0.6 | 2026-11-21 | 투약·귀가 API(34~36)와 상담 지연 입력 API(37)를 더함 | 태웅 |
| v0.7 | 2026-11-21 | 피드·앨범·사진 공개 범위 API(38~49)를 더함 | 태웅 |
| v0.7.1 | 2026-11-21 | 피드 업로드 크기 제한·권한 검사 순서·파일 삭제 시점을 맞춤 | 태웅 |
| v0.7.2 | 2026-11-23 | 과정 이야기를 걷어내고 문장을 다듬음. 원에 남은 답은 바로 답하지 않고 담임 카드 초안으로만 쓰도록 기획서·에이전트 명세(T14)에 맞춤 | 태웅 |
| v0.8 | 2026-11-23 | 11/20 강사 피드백을 반영함. 2장에 첫 시연 순서와 API별 상태 칸을, 3.19.1에 알림장 접수부터 발송 차단까지의 응답 예시를, 5.5에 먼저 쓰는 도구 세 개의 입력·출력·실패 뒤 행동을, 6.7에 인계 카드 저장 실패 사례를 더함. 3.22·3.23에 DB 모드 적재 결과(읽는 파일 종류·빈 파일·머리말·충돌·새 판·다시 적재)를 더하고, 3.29에 연결된 아이가 없는 학부모의 원 칸 권한을 더함. 문서 머리에 기준 판 표를 두고, 자료 올리기 크기 제한(2MiB·413)과 보류 예정일 경계를 코드에 맞춤 | 태웅 |
| v0.9 | 2026-11-24 | 문서 머리에 2차 검토 링크, 시연 코드 기준 커밋(`ab58b7c`), 1차 검토 뒤 보완 표(바뀐 내용·고친 절·지키는 시험·반영 커밋)를 더함. 코드에 맞춰 6.1에는 요청 처리 3분 마감 때 모델을 잠금 밖에서 부르고 늦은 결과를 버리는 규칙을, 3.3에는 거절 뒤 새 회신 카드를 초안 없이 만들어 직접 쓴 글로만 보내는 규칙을 적음 | 태웅 |
| v0.10 | 2026-11-24 | 위험 등급을 문의·상담에도 붙임(5.7). 문의·상담은 위험 낱말을 짧은 구로 보고(민원은 낱말 하나도 봄), 문의도 다시 분류할 수 있게 하고(3.14), 위험 기한(6.5)·알림 시각(6.6)·알림 제목(3.11)을 세 유형에 맞춤. 위험 상담의 원장 보고 카드는 예약 확정·반려 때 닫고, 판단 필요 상담도 담임이 확정·반려할 수 있음(3.4) | 태웅 |
| v0.10.1 | 2026-11-24 | 요청 대화의 메시지마다 쓴 사람의 역할(`sender_role`)을 더해, 화면에서 학부모 글과 담임 답을 나눠 그릴 수 있게 함(3.2·3.10·7장) | 태웅 |
| v0.11 | 2026-11-24 | 2차 의견 API 2·3, DB 3 반영. 배정 대기 표시·장애 결과 구분·MVP와 팀 확인 남음·동일 HEAD 계약 대조·시험 기준을 적고 참조 판을 맞춤 | 태웅 |
| v0.12 | 2026-11-24 | 요청 흐름 끝까지 점검(11/24) 반영. 학부모 추가 글을 담당자(없으면 원장)에게 알리고 답을 보낸 회신 카드는 빈 초안으로 다시 엶(3.10·3.3), 카드 상세에 대화 `messages`·이전 답 `previous_text`. AI 실패·시간 초과 인계 때도 위험 등급·담임 배정 유지(6.1). 권한 밖 질문은 고정 문구로 바로 안내(아이 일·위험·다툼은 제외). 상담: 희망 시간을 후보 계산에 반영, 원장 보고 확인(`acknowledge`), 확정 충돌 때 보존+새 후보. 투약·귀가: 반려 사유, 학부모 취소(API 50)·입력 수정(API 51), 값은 `requests.care_detail`. 알림 종류 6개(추가 글·재배정·상담 확정·알림장 정정·취소·반려). 알림장: 한도 초과 확인 `return_limit`, 초안 뒤 들어온 요청을 확인 항목으로, 반 카드 `note_batch`·작업 실패 표시, 보낸 알림장 정정(API 52, 판·정정 시각). 보류 재개·확인 만료는 주기 점검(beat)으로. 머리의 '11/27 시연' 문구를 뺌(시연은 12/08 중간 발표). 리뷰 반영: AI 실패로 넘기는 상담은 회신 카드 대신 시간 후보 카드로, 담임이 원장에게 올린 상담 보고는 확인(`acknowledge`) 대신 지시로만 닫음(6.1). | 태웅 |
| v0.13 | 2026-11-24 | [제안] 필수 동의 API 53~55·user.consents_complete·미동의자 6개 쓰기 경로 차단·새 오류 코드·현재 판 데모 시드를 추가하고 OpenAPI와 맞춤. | 태웅 |
| v0.13.1 | 2026-11-24 | 상담 재배정 때 새 담당 일정과 겹치는 후보를 버리고 부족한 만큼 다시 제안하며, 선택한 시간이 사라지면 학부모에게 다시 선택을 안내한다(3.16). 0012·0014를 되돌릴 때 이전 판에서 읽지 못하는 새 알림·이력·결정 행을 정리한다. | 태웅 |
| v0.13.2 | 2026-11-26 | 카드 목록·상세·재분류에 아이·보호자 이름을 더해요. GET /requests를 담임·원장에게 열고 담당 반·유형·답변 주체로 걸러요. 학부모 응답은 유지해요(3.7·3.9). | 태웅 |
| v0.13.3 | 2026-11-26 | [제안] 하루 중 기록 API 56~58·3.33과 API 22의 서버 기록 메모 fallback을 추가함. 기존 초안 요청·응답 칸은 유지함. | 태웅 |
| v0.13.4 | 2026-11-27 | [제안] 원 일정 API 63(3.35)·개인 알림 시간 API 64~65(3.36)·교직원 AI 질문 API 66(3.37)을 더함. 미동의 차단에 교직원 AI 질문을 넣어 일곱 경로. 목록 69개(DB 연결 35·제안 34) | 태웅 |
| v0.13.5 | 2026-11-27 | [제안] 재배정할 선생님 목록 API 70(3.38)을 더함. 원장만, 같은 기관 활성 선생님의 이름·지금 맡은 반만. 데모 시드에 반 없는 보조 교사 `teacher03`(…0203)을 더함. 목록 70개(DB 연결 35·제안 35) 지혜님 백엔드 정리 PM 체크: 본문 옛 숫자(52·56개)를 고치고 2.1의 A 화면·D 모델 칸을 11/27 리허설 기록(FB-021-1)으로 채움. | 태웅 |
| v0.13.6 | 2026-11-27 | [QA 전용] 알림장 다시 시험하기 API 71(3.39)을 더함. QA_TOOLS로만 켜며 한 반·날짜의 알림장·묶음 카드·이력·알림을 삭제하고 답장은 연결만 해제. 목록 71개(DB 연결 35·제안 36) | 태웅 |
| v0.13.7 | 2026-11-27 | [QA 전용] 사람별 QA 원 시드·전체 초기화 API 72·요청 trace API 73·배포 정보 API 74(3.40), QA 안내서를 더함. 목록 74개(DB 연결 35·제안 39) | 태웅 |
| v0.13.8 | 2026-11-27 | [제안] 아이 프로필 사진 API 75·급식 참고 사진 API 76·77(3.41)을 더하고, 반 아이 목록·내 정보·로그인의 아이에 profile_photo를 더함. 프론트가 임시로 쓰던 데모 아이 ID 고정 사진·다른 기관 공개 식단 사진을 서버 사진으로 바꿈. 목록 77개(DB 연결 35·제안 42) | 태웅 |
