import type { InboxFilter, RequestType, Risk, Status } from "./status";

/** 필드 이름은 임시다. 11/18 T10 계약 회의에서 정한 이름으로 바꾼다. */
export type Source = { doc: string; where: string; effective: string; old?: boolean };
export type Slot = { id: string; at: string; mode: "대면" | "전화"; picked: boolean };
export type HistoryItem = { at: string; who: string; what: string };
export type Role = "parent" | "teacher" | "director";

export type Card = {
  id: string;
  version?: number;
  kind?: string;
  inboxFilter?: InboxFilter;
  requestId: string;
  type: RequestType;
  status: Status;
  risk: Risk;
  urgentReason?: string;
  title: string;
  childName: string;
  guardianName: string;
  className: string;
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
  messages?: { id: number; fromParent: boolean; body: string; at: string }[];
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
