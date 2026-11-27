# db/seeds

햇살유치원 시연용 가상 계정·기관·반 데이터를 둡니다. 실제 원아 정보는 금지합니다.

기억 시드는 저장소 루트에서 아래 순서로 실행해요. DB 기동의 `SEED_DEMO=true` 경로도 같은 순서예요.

```bash
PYTHONPATH=apps/api python -m db.seeds.demo
PYTHONPATH=apps/api python -m db.seeds.documents
EMBEDDING_MODEL=BAAI/bge-m3 PYTHONPATH=apps/api python -m db.seeds.memories
```

`db.seeds.demo`는 끝에서 `db.seeds.photos`도 불러요. 가상 아이 프로필 사진 21장과 식단표 점심으로 만든 급식 참고 사진 38장을
`MEDIA_DIR/profiles/`·`MEDIA_DIR/meals/<원 ID>/`에 쓰고 `children.profile_photo_path`·`meal_photos`에 적어요. 사람별 QA 원도 같은 사진을 받아요.
원본은 `data/fixtures/kg-demo-01/profile_photos`·`meal_photos`이고, 이미 있는 행·파일은 덮지 않아요.

| 가상 데이터 | teacher01 | teacher02 | 그 밖 | 합계 |
| --- | ---: | ---: | ---: | ---: |
| 말투(`tone`, 80자 이내) | 10 | 6 | 0 | 16 |
| 업무 선호(`preference`) | 6 | 4 | 원장 3 | 13 |
| 거절 이유(`rejection_reason`) | 14 | 6 | 0 | 20 |
| 학부모 선호(`preference`) | 0 | 0 | 보호자 10명 × 2 | 20 |
| 규칙 | 활성 2·제안 1·거절 1 | 활성 1 | 0 | 5 |
| 승인 답변·완료 요청·완료 카드 | 별빛반 20·원 전체 10 | 0 | 0 | 각각 30 |
| 수정 후 승인(`edit_approve`) | 10 | 0 | 0 | 10 |

`memories`는 총 69개예요. 보호자는 parent01·parent02와 parent-c4-01·02·04·05·06·07·08·09예요.
개인 건강·가정사·실명·전화·계좌 번호나 아이 이름을 기억에 넣지 않아요. `structured`에는 시각·요일·연락 방식 등
기계가 읽는 값과 가상 표시를 넣어요. teacher01 말투 10개는 수정 승인 카드와 `structured.source=edit_approve`로 이어요.

`memory_rules`의 `(owner_id, reason_code)` 열린 규칙은 하나만 허용되므로 teacher01 활성 규칙은 상담 시간
(`after=14:00`, `before=17:00`)과 말투예요. 상담 계산은 `slot_unavailable`의 시각만 실제 적용해요.
teacher02는 15:00~17:30이에요. 빠진 정보 제안은 기존 `propose_rule`을 호출해 받은함 카드·이력도 만들어요.

승인 답은 [가상 기억 파일](../../data/fixtures/kg-demo-01/memories/memories.json)의 30개 질문이에요.
현재 30개 자료와 확장판 66개 자료에 공통으로 있는 문서만 인용해 단독 적용해도 근거가 있어요.
`saved_answer_sources`는 문서 연결 표이고, 정확한 조각은 완료 카드의 `card_evidence.chunk_id`로 이어요.
같은 내용 해시의 활성 문서와 인용문이 있는 조각을 찾지 못하면 해당 답과 완료 이력은 건너뛰어요.
질문 벡터는 기존 `embedding.embed`의 실제 bge-m3(1024차원)로 계산해요. 모델 설정·패키지·모델 로딩이 없으면
경고 한 줄을 남기고 승인 답만 건너뛰어요. 기억·규칙·완료 이력은 유지하며 모델을 켜고 재실행하면 빈 승인 답을 채워요.

완료 카드에는 보호자 질문·보낸 답, 승인 이력, 초안·승인·발송·완료 타임라인과 근거가 있어요.
날짜는 최초 실행 시점 기준 최근 3주에 나누고 재실행 때 옮기지 않아요. 요청·카드·답·일반 규칙은 고정 UUID,
기억은 DELETE API의 양수 조건에 맞춘 예약 bigint(990200001부터, 자동 증가 시퀀스는 유지),
제안은 JSON의 고정 `seed_key`로 중복을 막아요.
삭제된 기억의 빈 본문·삭제 시각, 사용자가 끄거나 거절한 규칙·승인 답은 복원하지 않아요.

검증: `bash tools/check.sh`, `bash tools/test_db.sh`. 새 DB 시험 6개는 전체 개수·재실행·삭제 보존,
계정별 HTTP 조회, 완료 받은함·수정 승인 출처, 상담 후보 제한, 사실·근거 일치, 모델·근거 누락을 확인해요.

현재 `GET /memories`는 `resources.py`의 담임 전용 권한 때문에 학부모에게 403을 돌려줘요.
학부모 preference 20개는 적재하고 저장소의 본인 범위를 시험하지만, 학부모 HTTP 조회 허용은 API 변경이 필요해요.

[제안] T54 시드는 mock과 같은 UUID의 반 글 2개·원 글 2개·가상 아이 JPEG 5장을 써요. MEDIA_DIR에 파일을 만들고, 재실행 때 기존 공개 범위와 삭제한 글은 복원하지 않아요. 0010 이전 판의 마이그레이션 시험에서는 피드 시드만 건너뛰어요.

0009에서 올린 DB도 피드 글을 처음 넣을 때만 family·class·org 예시를 맞춰요. 이후 가족이 바꾼 값은 보존해요. 삭제하지 않고 퇴소한 아이가 태그되지 않은 시드 사진의 파일이 없으면 해당 JPEG를 다시 써요. 옛 단색 PNG 해시인 행만 JPEG 경로·메타데이터로 갱신하고 태그와 다른 해시의 사진은 보존해요. 옛 PNG 파일은 지우지 않으며 고아 파일 정리가 맡아요.

`python -m db.seeds.demo`는 최초 적재일(KST) 기준 오늘·내일 15:00~15:30 확정 상담 2건과 어제 같은 시각의 완료 상담 1건에 요청·보호자 메시지·완료 카드·확정 후보·승인·이력·앱 알림을 함께 넣어요. 재실행 때 날짜·변경 상태를 보존하고, 바쁜 시간·기존 확정 예약과 겹치거나 보호자 연결이 끊긴 사례는 건너뛰어요. 고정 날짜 평가 자료와 기초 시드 함수 `seed_demo()`는 그대로예요.

`python -m db.seeds.demo`는 별빛반 20명에게 최초 적재일의 오늘·어제 관찰 기록을 각각 두 줄씩 넣어요(가상). 다시 실행해도 날짜·내용·삭제 표시를 보존하며 기초 `seed_demo()`와 고정 평가 픽스처에는 기록을 추가하지 않아요.
