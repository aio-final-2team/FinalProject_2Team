# apps/api/app/modules/documents

원 자료의 출처·시행일·공개 범위와 적재 정보를 관리합니다(T20, FR-04·FR-13·NFR-07).

| 파일 | 하는 일 |
| --- | --- |
| `documents.py` | 교직원 자료 목록(태웅). 아래 `ingest`의 올리기·상세를 함께 내보냄 |
| `ingest.py` | **자료 올리기(DB)**: 같은 내용이면 기존 문서(200), 아니면 문서 행을 만들고 조각 나누기·충돌 검사까지 끝낸 뒤 202. 충돌이면 `status = conflict_pending`이고 옛 판은 그대로 둠. 충돌 목록은 이력 `events(action='checked', detail.conflicts)`, 실패는 `events(tool_failed)`. 상세 조회 범위는 원장 전체·담임은 원 전체 + 지금 담당 반 |
| `search.py` | **`search_documents` 도구(DB)**: 낱말 검색. 사용 중·적재 완료·적용이 끝나지 않은 문서만(적용 전 자료도 찾되, 같은 점수면 지금 적용 중인 자료가 먼저), 학부모는 공개 범위 `parents`·`all`과 원 전체 + 아이 반 자료만. 결과 `chunks[] {chunk_id, document_title, location, effective_from, content, score}` |
| `parsing.py` | Markdown 원 자료를 읽어 머리말을 `documents` 열로 바꾸고, `## ` 제목 단위로 조각을 나눔. 제목이 근거 위치(`document_chunks.location`). 제목이 없으면 조각 하나, 위치 '본문' |
| `conflicts.py` | 새 문서와 사용 중인 문서를 비교해 같은 항목의 날짜·숫자가 다르면 충돌 목록을 냄. 규칙 기반이라 모델을 부르지 않음. 대상 반이 겹치는 문서끼리만 비교 |

## 정한 것 (11/23, 영민)

- 새 판의 이전 문서는 올리기 전에 담당 범위를 확인하고, 범위 밖이면 404와 거부 이력을 남겨요.
- 학부모 검색은 함수 안에서 아이의 반을 확인하며, 반을 생략하면 원 전체와 아이 반 자료만 찾아요.
- 같은 내용의 기존 문서도 담당 범위 밖이면 404로 거절해요.
- 중복 반은 한 번만 저장하고, 동시 올리기의 내용 중복은 기존 문서를 돌려줘요.
- 적재 실패 문서는 같은 내용으로 다시 올리면 새 파일 이름으로 다시 읽어요.
- 자료 파일은 2MiB까지만 받고 초과하면 413으로 거절해요.
- **검색은 낱말 검색부터**: 질문을 낱말로 나눠(조사 떼기) 찾은 비율(0~1)로 점수를 매기고, 같으면 제목·위치에 낱말이 있는 조각을 앞에 둬요. `document_chunks.embedding`은 비워 두고, bge-m3 벡터 검색은 T33에서 같은 함수 뒤에 붙여요. 알림장 시연에는 검색이 필요 없어요.
- **적재는 요청 안에서 바로**: 모델을 부르지 않는 가벼운 일이고, 파일 원문 열이 DB에 없어서 API·Celery 워커 어느 쪽에서도 같은 결과가 나오게 접수 요청 안에서 끝내요(모의 API와 같음). 무거운 임베딩은 저장된 조각을 읽어 뒤에서 할 거예요.
- 지금 읽는 파일은 `.md`·`.markdown`·`.txt`(UTF-8)뿐이에요. HWP·PDF는 `failed` + "지금은 .md·.txt 글 파일만 읽을 수 있어요".

## 원 자료 넣기

```sh
PYTHONPATH=apps/api python -m db.seeds.documents   # 데모 시드 뒤에
```

T11 가상 원 자료 다섯 폴더의 Markdown 30개 중 29개를 넣어요. 만 3세반(C3)만 대상인 `NT-2026-31`은 시드에 그 반이 없어 원 전체로 잘못 보이지 않게 넣지 않아요. 원 자료끼리 일부러 넣은 충돌(겨울방학 12/24 vs 12/26, 30문항 YC-F03)은 평가용이라 둘 다 사용 중으로 넣어요.

## 시험

- DB 없이: `tests/unit/test_documents_parsing.py`·`test_documents_conflicts.py`·`test_documents_search_terms.py`
- DB: `tools/test_db.sh tests/integration/db/test_documents_t20.py` — 적재 29개·위치·대상 반, 겨울방학 검색(위치·시행일), 학부모 반 범위·다른 기관·시행 전 자료, 충돌 올리기(`conflict_pending`+`conflicts[]`), 같은 내용 다시 올리기(200), 새 판(`superseded`), 읽을 수 없는 파일(`failed`), 다른 반 대상 올리기·상세(404)

## 임베딩·답변 초안 (T33)

기본은 낱말 검색과 모의 초안입니다. `apps/api/requirements-embedding.txt`를 별도로 설치하고
`EMBEDDING_MODEL=BAAI/bge-m3`로 설정하면 첫 사용 때 모델을 읽습니다. 원 자료를 넣은 뒤
`PYTHONPATH=apps/api python -m db.seeds.embed`로 빈 조각의 벡터를 채웁니다.
같은 판(`bge-m3@1`)의 벡터가 있는 조각은 낱말 점수와 코사인 유사도를 반씩 섞습니다.
벡터가 없거나 기능을 끄면 낱말 점수만 씁니다.

`ANSWER_WRITER=graph`면 위험도가 높지 않은 학부모 문의에 한해 자료 AI가 네 문서 종류를 찾습니다.
인용문이 실제 조각에 있는지 코드가 확인한 뒤 카드의 `card_evidence`에 저장합니다.
근거가 없거나 문서가 충돌하면 확인 문장으로 바꾸고 담임 카드에 넘깁니다.
실제 모델 호출에는 `OPENAI_API_KEY`와 `LLM_MODEL_DOCUMENT` 설정이 필요합니다.
