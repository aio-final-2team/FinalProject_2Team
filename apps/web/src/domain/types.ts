import type { InboxFilter, RequestIntent, RequestType, Risk, Status } from "./status";

/** 필드 이름은 임시다. 11/18 T10 계약 회의에서 정한 이름으로 바꾼다. */
export type Source = { doc: string; where: string; effective: string; old?: boolean };
export type Slot = { id: string; at: string; mode: "대면" | "전화"; picked: boolean };
export type HistoryItem = { at: string; who: string; what: string };
export type Role = "parent" | "teacher" | "director";

export type Card = {
  id: string;
  /** 요청 의도(알림·부탁). 목록 응답에서만 온다 */
  intent?: RequestIntent;
  version?: number;
  kind?: string;
  inboxFilter?: InboxFilter;
  requestId: string;
  /** 알림장 답장으로 접수된 문의면 그 알림장의 ID·날짜 (API 문서 3.34 source_note). 일반 요청은 없다 */
  sourceNote?: { note_id: string; note_date: string };
  type: RequestType;
  status: Status;
  risk: Risk;
  urgentReason?: string;
  title: string;
  childName: string;
  guardianName: string;
  /** 서버가 준 요청한 보호자 표시 이름(API 카드 응답 requester_name). 없으면 비어 있다 */
  requesterName?: string;
  className: string;
  /** 카드 목록이 주는 반 id(원장이 반을 고를 때 쓴다) */
  classroomId?: string;
  /** 목록 응답이 주는 담당자(상세 응답에는 없다) */
  assignee?: { id: string; name: string };
  createdAt: string;
  original: string;
  summary?: string;
  draft?: string;
  sources: Source[];
  check?: { passed: boolean; note?: string; issues?: string[]; attempt?: number };
  /** API warnings[]: stale_evidence · no_evidence · law_unchecked · check_unavailable · notify_failed */
  warnings?: string[];
  /** 초안 AI가 근거를 못 찾아 초안 없이 담임에게 넘긴 카드 (draft.no_evidence) */
  noEvidence?: boolean;
  repeatCount?: number;
  /** 학부모와 주고받은 글 전체(카드 상세 messages[]) */
  /** from: 학부모 · 선생님 · AI(권한 밖 고정 안내처럼 담임 승인 없이 나간 글) · 시스템 */
  messages?: { id: number; fromParent: boolean; from: "parent" | "teacher" | "ai" | "system"; body: string; at: string }[];
  /** 학부모가 글을 더 남겨 카드가 다시 열렸을 때 지난 답 (draft.previous_text). 이때 초안은 비어 있다 */
  previousText?: string;
  /** 개인 규칙 제안 카드(kind rule_proposal)의 규칙. 켜기(activate)·거절(decline)한다 */
  rule?: { id: string; reasonCode: string; text: string; status: string };
  escalated: boolean;
  assigned: boolean;
  parentConfirmedAt?: string;
  slots?: Slot[];
  groupedCount?: number;
  directorNote?: string;
  history: HistoryItem[];
};

export type CardAction =
  | { action: "approve_send"; draft?: string }
  | { action: "reject"; reason: string }
  /** 상담 시간을 거절하고 이유를 남긴다 → 서버가 새 후보를 계산한다 (API decision reject) */
  | { action: "reject_time"; reason: string }
  | { action: "hold"; reason: string; until: string }
  | { action: "escalate" }
  | { action: "resume" }
  | { action: "complete"; reason?: string }
  | { action: "reclassify"; risk: "normal" | "urgent"; reason: string; riskCategory?: "child_safety" | "staff_attack" | "legal_external" | "privacy_leak" }
  | { action: "confirm_slot"; slotId: string }
  | { action: "note"; text: string };

/** 카드가 받은함 필터 중 어디에 들어가는지 (T04 2.2). 서버가 계산할지 화면이 계산할지는 T10에서 정한다. */
export function filterOf(c: Card): InboxFilter {
  if (c.risk === "judge" && !["completed", "rejected"].includes(c.status)) return "judge";
  if (c.status === "classified" && !c.assigned) return "unassigned";
  if (c.status === "awaiting_review" || c.status === "escalated") return "review";
  if (c.status === "sent_or_booked" && c.type === "complaint" && c.parentConfirmedAt) return "review";
  if (c.status === "on_hold") return "hold";
  if (c.status === "completed" || c.status === "rejected") return "done";
  return "progress";
}

/** 확인 필요 안 정렬: 긴급 → 원장 보고 → 처리 완료 대기 → 오래된 순 */
export function reviewRank(c: Card): number {
  if (c.risk === "urgent") return 0;
  if (c.escalated) return 1;
  if (c.parentConfirmedAt) return 2;
  return 3;
}
