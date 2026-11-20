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
  check?: { passed: boolean; note?: string };
  repeatCount?: number;
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
