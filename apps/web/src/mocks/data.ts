import type { Card } from "@/domain/types";

/** 가짜 원 자료 (하늘반). 이름과 내용은 모두 예시다. */
const now = Date.now();
const ago = (min: number) => new Date(now - min * 60_000).toISOString();

const rule = { doc: "2026 운영 규정", where: "4장 2항", effective: "2026-03-01" };
const letter = { doc: "11월 가정통신문", where: "p.2", effective: "2026-11-01" };

export const seedCards = (): Card[] => [
  {
    id: "c-101", requestId: "r-5001", type: "complaint", status: "awaiting_review", risk: "urgent",
    urgentReason: "아이 안전", title: "하원 때 팔에 멍", childName: "이도윤", guardianName: "이도윤 보호자", className: "하늘반",
    createdAt: ago(10), original: "어제 하원 때 팔에 멍이 있었는데 무슨 일이 있었나요?", sources: [],
    escalated: true, assigned: true, history: [{ at: ago(10), who: "감독 AI", what: "긴급(아이 안전)으로 분류, 원장 보고 카드 함께 생성" }],
  },
  {
    id: "c-102", requestId: "r-5002", type: "complaint", status: "escalated", risk: "normal", title: "낮잠 시간",
    childName: "김하은", guardianName: "김하은 보호자", className: "하늘반", createdAt: ago(60),
    original: "낮잠 시간이 길어서 밤에 잠을 안 자요. 조금 줄여 주실 수 있을까요?",
    summary: "낮잠 시간 단축 요청. 같은 반 30일 안에 같은 주제 3번째.",
    draft: "안녕하세요, 하은 어머님. 낮잠은 운영 규정에 따라 13:00부터 14:30까지이고, 하은이는 14:00에 먼저 깨워 조용한 활동을 하도록 할게요.",
    sources: [rule, letter], check: { passed: true }, repeatCount: 3, escalated: true, assigned: true,
    directorNote: "규정은 유지하되 개별 기상 시간 조정은 허용해 주세요.",
    history: [
      { at: ago(60), who: "감독 AI", what: "민원 · 일반, 같은 주제 3번째로 원장 보고" },
      { at: ago(58), who: "검사 AI", what: "근거 2건 대조 통과" },
      { at: ago(30), who: "원장", what: "지시 남김" },
    ],
  },
  {
    id: "c-103", requestId: "r-4990", type: "complaint", status: "sent_or_booked", risk: "normal", title: "등원 차량 시간",
    childName: "박서준", guardianName: "박서준 보호자", className: "하늘반", createdAt: ago(60 * 26),
    original: "차량이 매일 10분씩 늦게 와요.", draft: "차량 출발 시간을 8:20으로 당겼어요.", sources: [rule],
    escalated: false, assigned: true, parentConfirmedAt: ago(120),
    history: [{ at: ago(60 * 24), who: "담임", what: "승인하고 보냄" }, { at: ago(120), who: "학부모", what: "확인했어요" }],
  },
  {
    id: "c-104", requestId: "r-5003", type: "consult", status: "awaiting_review", risk: "normal", title: "친구 관계 상담",
    childName: "김하은", guardianName: "김하은 보호자", className: "하늘반", createdAt: ago(60 * 20),
    original: "하은이 친구 관계 때문에 상담받고 싶어요.", sources: [], escalated: false, assigned: true,
    slots: [
      { id: "s1", at: "11/19(수) 15:00", mode: "대면", picked: true },
      { id: "s2", at: "11/20(목) 16:00", mode: "대면", picked: true },
      { id: "s3", at: "11/21(금) 10:00", mode: "전화", picked: false },
    ],
    history: [{ at: ago(60 * 19), who: "학부모", what: "가능한 시간 2개 고름" }],
  },
  {
    id: "c-105", requestId: "r-5004", type: "inquiry", status: "awaiting_review", risk: "normal", title: "겨울 방학 일정",
    childName: "최유나", guardianName: "최유나 보호자 외 2명", className: "하늘반", createdAt: ago(60 * 22),
    original: "겨울 방학이 언제부터인가요?", draft: "겨울 방학은 12월 29일(월)부터 1월 2일(금)까지예요.",
    sources: [{ doc: "2026 학사 일정", where: "1쪽", effective: "2026-03-01" }, { doc: "2025 학사 일정", where: "1쪽", effective: "2025-03-01", old: true }],
    check: { passed: true, note: "옛 판 자료 1건은 근거에서 뺐어요" }, groupedCount: 3, escalated: false, assigned: true,
    history: [{ at: ago(60 * 22), who: "감독 AI", what: "같은 질문 3건 묶음" }],
  },
  {
    id: "c-106", requestId: "r-5005", type: "complaint", status: "awaiting_review", risk: "judge", title: "선생님 말투",
    childName: "정민호", guardianName: "정민호 보호자", className: "하늘반", createdAt: ago(30),
    original: "선생님 말투가 걱정돼요. 아이가 무서워해요.", sources: [], escalated: true, assigned: true,
    history: [{ at: ago(30), who: "감독 AI", what: "교직원 비난 여부 확신 낮음 → 판단 필요" }],
  },
  {
    id: "c-107", requestId: "r-5006", type: "inquiry", status: "classified", risk: "normal", title: "차량 노선 변경",
    childName: "한지우", guardianName: "한지우 보호자", className: "하늘반", createdAt: ago(80),
    original: "이사해서 차량 노선을 바꾸고 싶어요.", sources: [], escalated: false, assigned: false, history: [],
  },
  {
    id: "c-108", requestId: "r-5007", type: "inquiry", status: "on_hold", risk: "normal", title: "겨울 특강 비용",
    childName: "오세린", guardianName: "오세린 보호자", className: "하늘반", createdAt: ago(60 * 30),
    original: "겨울 특강 비용이 얼마인가요?", sources: [], escalated: false, assigned: true,
    history: [{ at: ago(60 * 28), who: "담임", what: "보류 · 11/20까지 · 원장님 확인 필요" }],
  },
  {
    id: "c-109", requestId: "r-4980", type: "inquiry", status: "completed", risk: "normal", title: "현장 학습 준비물",
    childName: "김하은", guardianName: "김하은 보호자", className: "하늘반", createdAt: ago(60 * 72),
    original: "현장 학습 때 무엇을 챙기면 되나요?", draft: "도시락, 물, 여벌 옷을 챙겨 주세요.", sources: [letter],
    escalated: false, assigned: true, history: [],
  },
];
