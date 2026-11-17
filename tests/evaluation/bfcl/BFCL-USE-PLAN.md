# BFCL 원본 활용 계획 (2팀 유치온)

> 작성일: 2026-11-17 · 담당: 인혜(T05), 영민(협업) · 근거: 강사님 [BFCL-PREPARE.md](https://gt.isitsoft.kr/publicproj/aio-01d4-stu/src/branch/main/Lecture/FinalProject/Data/BFCL-PREPARE.md) 0·9~14절, [SUBJECTS-4TEAM.md](SUBJECTS-4TEAM.md)
>
> **상태: 강사님 실행 대기.** 실행기는 강사님 것(`Lecture/FinalProject/Data/BFCL-PREPARE/bfcl_original.py`)을 쓰며, 2026-11-17 현재 수업 저장소에 아직 배포되지 않았다. 강사님이 먼저 실행한 뒤, 필요하면 팀이 같은 실행기로 다시 실행한다. 이 문서의 어떤 숫자도 모델 실행 결과가 아니다.

## 1. 목적과 범위

- 팀이 쓸 LLM(**gpt-6-luna 하나**, 팀 결정)의 기본 함수 호출 능력(맞는 함수·인자 선택, 관련 없는 질문에 호출 안 하기)을 BFCL 원본 문제로 확인한다.
- 유치온 서비스 품질은 이 평가로 판단하지 않는다. 서비스 업무는 팀 자체 30문항(`data/evaluation/2팀_유치온_자체평가_30문항.md`)으로, 실제 동작은 서비스 연동 시험으로 따로 본다.
- 보고서에는 **"BFCL 원본 30문항 부분 집합 평가"**라고 적는다. 전체 BFCL·공식 리더보드 점수로 표현하지 않는다.

## 2. 결과 구분 (별도 표·별도 분모, NFR-09)

| 평가 묶음 | 문항 | 결과 구분 | 누가 실행 | WBS |
|---|---|---|---|---|
| 공통 원본 | BFCL 원본 30문항 | `bfcl_subset` (강사님 실행분은 `instructor_baseline`) | 강사님 먼저, 이후 팀 | T05 |
| 팀 자체 | 유치온 시나리오 30문항 | `team_domain` | 팀 | T06 설계 (~11/18), T41 실행 (12/07~08) |
| 서비스 연동 | 같은 시나리오를 구현된 서비스에서 실행 | `team_e2e` | 팀 | T65 통합 테스트 |

세 결과를 합산하지 않는다. 강사님 실행 결과를 팀이 직접 실행한 것처럼 표시하지 않는다.

## 3. 고정 원본 (강사님 문서 10절)

| 항목 | 값 |
|---|---|
| 데이터셋 | [gorilla-llm/Berkeley-Function-Calling-Leaderboard](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard) |
| revision | `61fc0608cfd831fcfbbaa676ebdfef0ed963eeda` |
| 라이선스 | Apache-2.0 |
| 범주 | simple 400 · multiple 200 · irrelevance 240 = 840문항 (BFCL 전체 문항 수가 아님) |
| irrelevance 정답 | 정상 완료 응답에서 함수 호출 0개면 통과 |

### 파일 해시·건수 (2026-11-17 팀이 직접 받아 확인, 강사님 실행 결과와 대조용)

| 파일 | 건수 | SHA-256 |
|---|---:|---|
| `BFCL_v3_simple.json` | 400 | `fbc37b2ad252bf9af985582e0e07b456173fe627d957491472ea9cef5fb83158` |
| `BFCL_v3_multiple.json` | 200 | `aef168155ebd74b7ac2401198b201343bc7d16d7a3d7e0d4e6d8ee82c6969b2a` |
| `BFCL_v3_irrelevance.json` | 240 | `975f51c51f688649fd190078efd87081241e0a326f9114a2ea3c1ca2440d8690` |
| `possible_answer/BFCL_v3_simple.json` | 400 | `2911a2bc00df82c4f999ffa64fedb0164cb88e96212ffa5972087eb91fd496ee` |
| `possible_answer/BFCL_v3_multiple.json` | 200 | `244e00ce9395df948bcafc7bee64e8f9c87ef70887587d83cae45b13699f3047` |

건수는 강사님 문서와 일치한다. 강사님 실행 결과의 `SOURCE-MANIFEST.json` 해시와 같은지 확인한다.

## 4. 고정 30문항

| 범주 | ID |
|---|---|
| simple | simple_149, simple_170, simple_181, simple_221, simple_242, simple_257, simple_302, simple_309, simple_367, simple_399 |
| multiple | multiple_123, multiple_134, multiple_14, multiple_16, multiple_170, multiple_178, multiple_20, multiple_24, multiple_53, multiple_69 |
| irrelevance | irrelevance_134, irrelevance_16, irrelevance_170, irrelevance_178, irrelevance_20, irrelevance_203, irrelevance_32, irrelevance_68, irrelevance_86, irrelevance_87 |

연결 시험(smoke) 3문항: `simple_149`, `multiple_123`, `irrelevance_134`. 결과를 본 뒤 ID를 바꾸지 않는다.

## 5. 실행 순서 (강사님 실행 이후 팀이 할 때)

강사님 문서 10~11절 명령을 그대로 따른다. 강사님 실행기는 Gemini 호출로 되어 있으므로, 팀 실행 시 **AI를 부르는 부분만 OpenAI로 바꾸고 시험지·정답지·채점기는 그대로 둔다.**

1. 모델 없이 점검: `prepare` → "Prepared 30 cases", `self-test` → "self-test passed"
2. 3문항 맛보기(`--smoke`): 호출이 되는지, 응답에 찍힌 모델 이름이 맞는지 확인
3. 30문항 본시험: gpt-6-luna 한 번
4. API 키는 저장소 루트 `.env`에만 넣는다(Git 제외). 키를 문서·캡처·결과에 남기지 않는다.
5. 호출이 안 되면 오류를 그대로 적고 '미확정'으로 둔다. 결과를 만들어 채우지 않는다.

## 6. 채점 기준 (강사님 교육용 채점기 `educational-bfcl-v3-subset-1`)

| 항목 | 판정 |
|---|---|
| simple·multiple | 호출 정확히 1개, 함수 이름이 정답과 같음 |
| 인자 | 필수 인자·추가 인자·중첩 타입·enum 검사. 문자열 숫자를 숫자로 바꾸지 않음 |
| 허용값 | 정답 목록 중 하나와 같음. 배열 순서 유지, 문자열은 대소문자·공백까지 정확히 |
| 선택 인자 생략 | required가 아니고 정답에 생략 표지가 있을 때만 허용. 실제 빈 문자열은 실패 |
| irrelevance | 정상 완료 응답에서 호출 0개면 통과 |
| API·변환·파싱 실패 | ERROR. 분모에서 빼지 않음 |

공식 AST 평가기와 같은 구현·점수가 아니다.

## 7. 기록표 (gpt-6-luna 한 장)

| 항목 | 값 |
|---|---|
| 실행 주체 | 강사님 / 팀 (구분해서 따로 적음) |
| 요청한 모델 이름 | gpt-6-luna |
| 응답에 찍힌 모델 이름 | |
| 실행 시각 | |
| PASS · FAIL · ERROR | / / (30문항 기준) |
| 실행 ID (run_id) | |
| 화면 캡처 3장 | ① 데이터 출처·실행 명령 ② 범주별 결과 ③ 대표 정답·오답의 원문·기대값·실제 호출 |
| 상태 | 완료 / 미확정 (오류 원문) |

smoke 3문항 결과는 본시험과 합산하지 않는다. 결과 파일(`run.json`, `RESULTS.csv`, `SUMMARY.md`, 문항별 request/raw/result)은 검토 후 제출용만 `Docs/Step2/` 아래로 옮긴다.

## 8. 팀이 정할 것

1. 강사님 실행 결과를 받은 뒤 팀이 다시 실행할지, 언제·누가 할지
2. gpt-6-luna의 실제 API 모델 ID 확인 (응답에 찍힌 이름 기준)
3. 제출용 증빙 위치 (`Docs/Step2/` 아래 폴더 이름)

## 9. 보고 문구 (실제 실행 후에만 사용)

> BFCL 원본 중 simple·multiple·irrelevance 세 범주 840문항에서 범주별 10개씩 총 30문항을 고정 revision으로 선정하여, gpt-6-luna에 실행하고 원본 정답을 이용한 교육용 채점기로 평가했다. 이는 전체 BFCL이나 공식 리더보드 평가를 의미하지 않으며, 해당 표본에서의 관측 결과다.

실행 전에는 "강사님 실행 대기"라고만 기록한다.
