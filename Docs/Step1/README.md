# 유치온 Step 1 — 기획서와 WBS

프로젝트 범위와 일정의 기준 문서를 모아 둔 폴더입니다. 검토 시 Word·Excel 원본을 우선하고, 빠른 검색에는 UTF-8 Markdown을 이용하세요.

## 최신 문서 (2026-11-24)

| 확인할 내용 | Word·Excel 원본 | Markdown 열람용 |
|---|---|---|
| 서비스 정의·요구사항·검증 기준 | [기획서 Word](기획서.docx) | [기획서 Markdown](기획서.md) |
| 담당자·일정·선행 작업·진척 현황 | [WBS Excel](WBS.xlsx) | [WBS Markdown](WBS.md) |

이 폴더에는 위 네 파일만 최신 기준 문서로 둡니다. 11/16·11/17 날짜 판은 [이전판/](이전판/)에 옮겨 두었고, 당시 기록으로만 봅니다.

## 2차 검토 링크와 시연 기준 커밋

| 항목 | 내용 |
|---|---|
| 2차 검토 링크 | `develop` 브랜치의 [기획서](https://github.com/aio-final-2team/FinalProject_2Team/blob/develop/Docs/Step1/기획서.md) · [WBS](https://github.com/aio-final-2team/FinalProject_2Team/blob/develop/Docs/Step1/WBS.md) · [T17 숫자·출처 검증표](https://github.com/aio-final-2team/FinalProject_2Team/blob/develop/Docs/Step3/T17_숫자_출처_검증표.md). 설계서별 링크는 [레포 README](../../README.md#2차-검토-문서)에 모았습니다 |
| 시연 코드 기준 커밋 | [레포 README '2차 검토 문서'](../../README.md#2차-검토-문서)의 '시연 코드 기준 커밋' 한 줄을 봅니다. 11/27 알림장 시연에 쓰는 팀 서버 커밋이고, 값은 그 한 줄에만 둡니다 |

## 핵심 반영 내용

### 2026-11-16 기준 반영

- 기획서·WBS에 필수·선택 범위와 선택 기능의 회귀 대응 조건을 정리했습니다.
- 당시 계획은 중간 발표 전 제공 VM 사용 후 AWS 이전이었습니다. 이 배포 결정은 2026-11-17에 변경되어, 최신 기준은 아래 날짜 항목을 따릅니다.
- 12/24 브라우저 웹 URL은 앱 설치 없이 실행하는 별도 제출물이며, Android 앱과 기능·서버를 재사용하도록 정리했습니다.
- 생성 모델 실제 호출 확인, AC-06 권한 시험과 AC-11 베타 피드백의 작업·증거 연결, STEP 1 마감·업로드·보완 날짜 구분을 반영했습니다.
- 원장 현황은 같은 React 앱의 역할별 화면으로 통합했습니다. 브라우저 웹과 Android가 코드와 API 서버를 공유하며 별도 대시보드 서비스는 배포하지 않습니다.

### 2026-11-17 추가 반영

- 배포는 첫 배포부터 AWS EC2를 기준으로 변경했습니다. AWS 접근이 늦으면 12/24 웹 URL에 제공 VM을 임시 대안으로 사용하고, 선택 사진 AI는 목업으로 시연합니다.
- 4차 결정 D24–D26을 기록했습니다. 선택 기능 착수는 12/9 한 번 판단하고, 담당자의 필수 작업이 제때 진행될 때 시작합니다. 보류는 T60 → T59 → T56 → T50 순서이며 동결 전 재개 여부를 판단합니다.
- D27에 따라 생성 모델은 `gpt-6-luna`로 유지합니다. T05 비교는 평가 세트별로 기록했습니다: BFCL 화면 결과 Luna 24/30·mini 21/30, 팀 공식 v0.3 Luna 21/30·mini 12/30, 자체 v0.5 각 19/30. 첨부 ZIP의 BFCL 요약은 화면 점수와 달라 두 결과를 구분해 보존하고 추가 대조 대상으로 표시했습니다.
- T50 계획 공수는 총 16시간(개발 0·검토 2·통합·시험 14)으로 확정했습니다. 해당 담당자의 역할이 개발이 아니기 때문입니다. T56은 8·4·4시간, T59와 T60은 각각 3·3·2시간으로 나눴습니다.

### 2026-11-18 추가 반영

- 1117 기획서·WBS의 Word·Excel·Markdown과 T05 BFCL 평가 증빙을 `develop`에 반영했습니다. [#237](https://github.com/aio-final-2team/FinalProject_2Team/pull/237) · [#239](https://github.com/aio-final-2team/FinalProject_2Team/pull/239)
- 1116 기획서·WBS에도 첫 배포부터 AWS EC2를 사용하는 기준과 배포 준비 작업을 반영했습니다. 1117 문서에는 GPT 모델 13개 반복 실측과 비용 비교를 추가했고, D27의 기본 모델은 `gpt-6-luna`로 유지했습니다. BFCL 화면 요약(24:21)과 ZIP 결과(21:21)는 서로 다른 실행의 `strict` 설정에서 나온 값임을 확인했습니다. [#244](https://github.com/aio-final-2team/FinalProject_2Team/pull/244)
- T04 업무 흐름과 권한 기준을 1117 기획서 Word·Markdown에 반영했습니다. WBS에는 담당 성주, 검토 지혜, 실제 시작 11/17, 실제 완료 11/18을 기록하고 상태와 간트를 완료로 갱신했습니다. [참고 #234](https://github.com/aio-final-2team/FinalProject_2Team/pull/234) · [문서 병합 #244](https://github.com/aio-final-2team/FinalProject_2Team/pull/244)
- 1117 WBS의 T06 요구사항에 AC-07을 추가했습니다. BFCL과 팀 자체 평가는 별도 분모로 채점하고, T05 반복 실측에 사용한 팀 v0.3과 #235의 v0.5 평가 자료를 구분해 기록했습니다. [참고 #235](https://github.com/aio-final-2team/FinalProject_2Team/pull/235) · [문서 병합 #244](https://github.com/aio-final-2team/FinalProject_2Team/pull/244)
- [피드백 안내](../Feedback/README.md)에 담당자별 메모 폴더와 `[문서]`·`[작업]` 항목의 처리 절차를 정리했습니다. [#240](https://github.com/aio-final-2team/FinalProject_2Team/pull/240) · [#241](https://github.com/aio-final-2team/FinalProject_2Team/pull/241) · [#243](https://github.com/aio-final-2team/FinalProject_2Team/pull/243)

- FB-001-5의 AWS 개발 기간 비용 추정(약 $133)과 실제 청구액 확인 방법을 기획서 §11에, 크레딧 초과 위험과 대응을 §10에 반영했습니다. WBS T66에는 개발 기간 추정치·실제 청구액·유치원 운영 월비용을 구분하는 기준을 추가했습니다. [원본 메모 PR #242](https://github.com/aio-final-2team/FinalProject_2Team/pull/242) · [통합 PR #259](https://github.com/aio-final-2team/FinalProject_2Team/pull/259) · [반영 메모](../Feedback/jihye/FB-001-5.md)

### 2026-11-24 추가 반영 (강사님 11/24 피드백 FB-020)

- 11/16·11/17 날짜 판 기획서·WBS 8개 파일을 [이전판/](이전판/)으로 옮기고, 기획서·WBS Markdown 머리의 원본 표시를 `기획서.docx`·`WBS.xlsx`로 고쳤습니다. 2차 검토 링크와 시연 기준 커밋을 보는 곳을 위 표에 적었습니다. [메모](../Feedback/jihye/FB-020-9.md)

## 문서 갱신 기준

Word와 Excel 원본을 기준으로 관리합니다. Markdown은 각각 DOCX·XLSX에서 생성한 UTF-8 열람용 사본이며, 원본을 수정하면 Markdown도 함께 갱신합니다. 날짜가 있는 핵심 반영 내용은 당시 결정과 최신 결정을 구분해 기록합니다.
