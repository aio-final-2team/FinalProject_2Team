/**
 * T04 공통 상태와 화면 표시 이름 (Docs/Step2/유치온_T04_흐름권한명세.md 2장).
 * 화면은 상태 이름을 직접 쓰지 않고 항상 이 표를 거친다. 그래야 화면마다 이름이 달라지지 않는다.
 */
export const STATUSES = [
  "received",
  "classified",
  "needs_info",
  "assigned",
  "awaiting_review",
  "escalated",
  "on_hold",
  "approved",
  "sent_or_booked",
  "completed",
  "rejected",
] as const;
export type Status = (typeof STATUSES)[number];

/** 상태 색은 브랜드 색만 쓴다: 할 일 = 블루, 답 왔음 = 라벤더, 완료 = 민트, 기다림 = 회색, 긴급 = 네이비 채움 */
export type Tone = "action" | "answered" | "done" | "wait" | "urgent";

type Label = { label: string; tone: Tone };

export const PARENT_LABEL: Record<Status, Label> = {
  received: { label: "접수됨", tone: "wait" },
  classified: { label: "접수됨", tone: "wait" },
  needs_info: { label: "정보가 더 필요해요", tone: "action" },
  assigned: { label: "선생님께 전달됨", tone: "wait" },
  awaiting_review: { label: "선생님 확인 중", tone: "wait" },
  escalated: { label: "원장님 확인 중", tone: "wait" },
  on_hold: { label: "확인이 늦어지고 있어요", tone: "wait" },
  approved: { label: "선생님 확인 완료", tone: "answered" },
  sent_or_booked: { label: "답변 도착", tone: "answered" },
  completed: { label: "완료", tone: "done" },
  rejected: { label: "처리할 수 없는 요청", tone: "wait" },
};

export const STAFF_LABEL: Record<Status, Label> = {
  received: { label: "접수", tone: "wait" },
  classified: { label: "미배정", tone: "wait" },
  needs_info: { label: "학부모 응답 대기", tone: "wait" },
  assigned: { label: "준비 중", tone: "wait" },
  awaiting_review: { label: "확인 필요", tone: "action" },
  escalated: { label: "원장 보고", tone: "action" },
  on_hold: { label: "보류", tone: "wait" },
  approved: { label: "승인됨", tone: "answered" },
  sent_or_booked: { label: "발송됨", tone: "answered" },
  completed: { label: "완료", tone: "done" },
  rejected: { label: "반려", tone: "wait" },
};

export type RequestType = "inquiry" | "consult" | "complaint";
export const TYPE_LABEL: Record<RequestType, string> = { inquiry: "문의", consult: "상담", complaint: "민원" };

/** 민원 위험 등급 (T04 2.3). 학부모에게는 보이지 않는다. */
export type Risk = "normal" | "urgent" | "judge";

/** 교직원 받은함 필터 6개 (T04 2.2, 합의 5) */
export const INBOX_FILTERS = [
  { key: "review", label: "확인 필요" },
  { key: "judge", label: "판단 필요" },
  { key: "unassigned", label: "미배정" },
  { key: "hold", label: "보류" },
  { key: "progress", label: "진행 중" },
  { key: "done", label: "완료" },
] as const;
export type InboxFilter = (typeof INBOX_FILTERS)[number]["key"];
