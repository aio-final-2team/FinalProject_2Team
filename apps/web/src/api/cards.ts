import { useLiveStream } from "./stream";
import { useMutation, useQueries, useQuery, useQueryClient } from "@tanstack/react-query";
import type { InboxFilter, RequestType, Status } from "@/domain/status";
import type { Card, CardAction, HistoryItem, Role, Slot, Source } from "@/domain/types";
import { useSession } from "@/app/session";
import { api, uuid } from "./client";
import { term } from "@/domain/wording";

type ApiRequestType = "inquiry" | "consultation" | "complaint";
type ApiInboxFilter = "unassigned" | "needs_review" | "uncertain" | "on_hold" | "in_progress" | "done";
type Person = { id: string; display_name: string };
type Period = { start: string; end: string };
type CardItem = {
  id: string; kind: string; status: string; status_label: string; version: number;
  request_id: string | null; request_type: ApiRequestType | null; title: string;
  urgency: string | null; risk_level: string | null; risk_category: string | null; is_urgent: boolean;
  repeat_count: number | null; check: { passed: boolean; issue_count: number } | null;
  parent_choice_count: number | null; classroom: { id: string; name: string }; assignee: Person | null;
  due_at: string | null; is_delayed: boolean; hold_until: string | null;
  /** 요청이 있는 카드에서만 온다. 서버가 아직 안 주면 없다 */
  child_name?: string | null; requester_name?: string | null;
};
type CardList = {
  total: number; page: number; size: number; items: CardItem[];
  counts: Record<ApiInboxFilter, number>; type_counts: Record<string, number>;
};
type CardDetail = {
  card: { id: string; kind: string; status: string; version: number; summary: string; draft: Record<string, unknown>; check_result: { passed?: boolean; issues?: unknown[]; note?: string; attempt?: number } | null; check_attempts: number };
  request: null | { child_name?: string | null; requester_name?: string | null; id: string; type: ApiRequestType | "pickup"; title: string | null; body: string; status: Status; risk_level: string | null; risk_category: string | null; repeat_count: number | null; parent_confirmed_at: string | null; source_note?: { note_id: string; note_date: string } | null; classroom_id: string; created_at: string; updated_at: string };
  evidence: Array<{ document_title: string; location: string | null; effective_from: string | null; quote: string; is_current: boolean }>;
  warnings: string[];
  messages?: Array<{ id: number; sender_type: string; sender_role?: string | null; body: string; created_at: string }>;
  rule?: null | { id: string; reason_code: string; rule_text: string; status: string };
  parent_choices: Array<{ slot_id: number; period: Period; room: string; chosen_at: string; hold_expires_at: string }>;
  director_instruction: null | { text: string; by: Person; at: string };
  timeline: Array<{ action: string; actor_type: string; agent_name: string | null; created_at: string }>;
};

/** 서버의 위험 분류 코드를 교사가 읽는 말로 바꾼다 (API RiskCategory) */
const RISK: Record<string, string> = { child_safety: "아이 안전", staff_attack: "교직원 대상 폭언", legal_external: "법적·외부 대응", privacy_leak: "개인정보 유출" };
const riskLabel = (c?: string | null) => (c ? (RISK[c] ?? c) : undefined);
export type TypeFilter = "all" | "complaint" | "consultation" | "inquiry" | "rule";
export type CardsResult = { items: Card[]; counts: Record<InboxFilter, number>; typeCounts: Record<TypeFilter, number> };
const UI_TO_API_FILTER: Record<InboxFilter, ApiInboxFilter> = { review: "needs_review", judge: "uncertain", unassigned: "unassigned", hold: "on_hold", progress: "in_progress", done: "done" };
const API_TO_UI_FILTER: Record<ApiInboxFilter, InboxFilter> = { needs_review: "review", uncertain: "judge", unassigned: "unassigned", on_hold: "hold", in_progress: "progress", done: "done" };
const requestType = (value: ApiRequestType | "pickup" | null | undefined): RequestType => value === "consultation" ? "consult" : value === "complaint" ? "complaint" : "inquiry";
const risk = (value: string | null | undefined) => (value === "urgent" ? "urgent" : value === "uncertain" ? "judge" : "normal") as Card["risk"];

const statusFromItem = (item: CardItem, filter: InboxFilter): Status => {
  if (filter === "unassigned") return "classified";
  if (filter === "hold") return "on_hold";
  if (filter === "done") return item.status === "rejected" ? "rejected" : "completed";
  if (item.status === "done") return "completed";
  return item.risk_level === "urgent" ? "escalated" : "awaiting_review";
};

const cardFromItem = (item: CardItem, filter: InboxFilter): Card => ({
  id: item.id, version: item.version, kind: item.kind, inboxFilter: filter,
  requestId: item.request_id ?? "-", type: requestType(item.request_type), status: statusFromItem(item, filter), risk: risk(item.risk_level),
  urgentReason: riskLabel(item.risk_category), title: item.title || term(item.status_label), childName: item.child_name ?? "", guardianName: item.requester_name ?? "보호자", requesterName: item.requester_name ?? undefined,
  className: item.classroom.name, classroomId: item.classroom.id, createdAt: item.due_at ?? new Date().toISOString(), original: item.title, sources: [],
  check: item.check ? { passed: item.check.passed, note: item.check.issue_count ? `확인 항목 ${item.check.issue_count}개` : undefined } : undefined,
  repeatCount: item.repeat_count ?? undefined, escalated: item.risk_level === "urgent" || item.kind === "director_report",
  assignee: item.assignee ? { id: item.assignee.id, name: item.assignee.display_name } : undefined,
  assigned: !!item.assignee, slots: item.parent_choice_count ? [] : undefined, history: [],
});

const formatPeriod = (period: Period) => new Date(period.start).toLocaleString("ko-KR", { month: "numeric", day: "numeric", weekday: "short", hour: "2-digit", minute: "2-digit" });
const AGENT_NAME: Record<string, string> = { supervisor: "감독", document: "자료", checker: "검사", memory: "기억" };
/** 학부모가 하는 동작. 서버는 행위자 종류를 user로만 주어서, 동작으로 학부모와 교직원을 가른다 */
const PARENT_ACTIONS = new Set(["created", "message_added", "cancelled", "care_updated", "parent_confirmed", "slots_chosen"]);
const actorName = (actor: string, agent: string | null, action: string) =>
  agent ? `${AGENT_NAME[agent] ?? ""} AI`.trim() : actor === "user" ? (PARENT_ACTIONS.has(action) ? "학부모" : "교직원") : actor === "agent" ? "AI" : "시스템";
/** 처리 이력의 action 코드를 교직원이 읽는 말로 바꾼다. 모르는 코드는 내부 용어를 그대로 보이지 않는다 */
const ACTION_LABEL: Record<string, string> = { created: "접수", classified: "분류", assigned: "담당 배정", drafted: "초안 작성", checked: "검사", approved: "승인", sent: "보내기", rejected: "거절", dismissed: "거절", held: "보류", resumed: "재개", escalated: "원장 보고", completed: "처리 완료", risk_reclassified: "위험 분류 변경", message_added: "글 추가", cancelled: "취소", care_updated: "입력 수정" };
const actionLabel = (a: string) => ACTION_LABEL[a] ?? "처리 기록";

/** 판단 필요 카드에는 감독 AI가 쓴 이유 한 줄(card.draft.risk_reason)이 올 수 있다. 없으면 화면이 기본 문구를 쓴다 */
export type CardWithReason = Card & { riskReason?: string };

const cardFromDetail = (data: CardDetail): CardWithReason => {
  const req = data.request;
  const sources: Source[] = data.evidence.map((e) => ({ doc: e.document_title, where: e.location ?? "", effective: e.effective_from ?? "", old: !e.is_current }));
  const slots: Slot[] | undefined = data.parent_choices.length ? data.parent_choices.map((s) => ({ id: String(s.slot_id), at: formatPeriod(s.period), mode: "대면", picked: true })) : undefined;
  const history: HistoryItem[] = data.timeline.map((e) => ({ at: e.created_at, who: actorName(e.actor_type, e.agent_name, e.action), what: actionLabel(e.action) }));
  const draft = typeof data.card.draft.text === "string" ? data.card.draft.text : undefined;
  return {
    id: data.card.id, version: data.card.version, kind: data.card.kind, requestId: req?.id ?? "-", sourceNote: req?.source_note ?? undefined, type: requestType(req?.type),
    status: req?.status ?? (data.card.status === "done" ? "completed" : "awaiting_review"), risk: risk(req?.risk_level),
    urgentReason: riskLabel(req?.risk_category), title: req?.title ?? data.card.summary, childName: req?.child_name ?? "", guardianName: req?.requester_name ?? "보호자", requesterName: req?.requester_name ?? undefined,
    className: "", createdAt: req?.created_at ?? new Date().toISOString(), original: req?.body ?? data.card.summary,
    summary: data.card.summary || undefined, draft: draft || undefined, sources,
    messages: data.messages?.map((m) => ({ id: m.id, fromParent: m.sender_role === "parent", from: m.sender_role === "parent" ? "parent" : m.sender_type === "agent" ? "ai" : m.sender_type === "system" ? "system" : "teacher", body: m.body, at: m.created_at })),
    rule: data.rule ? { id: data.rule.id, reasonCode: data.rule.reason_code, text: data.rule.rule_text, status: data.rule.status } : undefined,
    previousText: typeof data.card.draft.previous_text === "string" && data.card.draft.previous_text ? data.card.draft.previous_text : undefined,
    check: data.card.check_result ? { passed: !!data.card.check_result.passed, note: data.card.check_result.note, issues: (data.card.check_result.issues ?? []).map(issueText).filter(Boolean), attempt: data.card.check_result.attempt } : undefined,
    warnings: data.warnings ?? [], noEvidence: !!data.card.draft?.no_evidence,
    riskReason: typeof data.card.draft.risk_reason === "string" && data.card.draft.risk_reason.trim() ? data.card.draft.risk_reason.trim() : undefined,
    repeatCount: req?.repeat_count ?? undefined, escalated: req?.status === "escalated" || data.card.kind === "director_report",
    assigned: true, parentConfirmedAt: req?.parent_confirmed_at ?? undefined, slots, directorNote: data.director_instruction?.text, history,
  };
};

export const useCards = (filter: InboxFilter, type: TypeFilter = "all") => {
  const role = useSession().user?.role;
  const teacher = role === "teacher";
  return useQuery({
    queryKey: ["cards", "list", filter, type, role],
    queryFn: async (): Promise<CardsResult> => {
      const apiFilter = UI_TO_API_FILTER[filter];
      /* 교사는 원장 보고 카드를 처리하지 못한다(API 403). 같은 요청의 답장 카드와 겹쳐 두 줄로 보이므로 목록에서 뺀다.
         빼고 나면 서버가 준 종류별 숫자가 맞지 않아서, 교사는 종류 없이 받아 온 뒤 화면에서 나누고 숫자도 다시 센다 */
      const result = await api<CardList>(`/api/v1/cards?filter=${apiFilter}&size=100${type === "all" || type === "rule" || teacher ? "" : `&request_type=${type}`}`);
      const counts = Object.fromEntries(Object.entries(result.counts).map(([key, value]) => [API_TO_UI_FILTER[key as ApiInboxFilter], value])) as Record<InboxFilter, number>;
      const typeCounts = { all: 0, complaint: 0, consultation: 0, inquiry: 0, rule: 0, ...((result as { type_counts?: Partial<Record<TypeFilter, number>> }).type_counts ?? {}) };
      if (!teacher) return { items: result.items.map((item) => cardFromItem(item, filter)), counts, typeCounts };
      const own = result.items.filter((item) => item.kind !== "director_report");
      /* 규칙 제안 카드는 학부모 문의가 아니라서 문의·상담·민원 숫자에 넣지 않고 따로 센다 */
      const isRule = (item: CardItem) => item.kind === "rule_proposal";
      /* 화면은 민원·상담이 아닌 요청을 모두 문의로 보여 주므로(requestType) 숫자도 같은 기준으로 센다 */
      const typeOf = (item: CardItem) => requestType(item.request_type);
      const byType = (t: Exclude<TypeFilter, "all" | "rule">) => own.filter((item) => !isRule(item) && typeOf(item) === (t === "consultation" ? "consult" : t)).length;
      const recount = { all: own.length, complaint: byType("complaint"), consultation: byType("consultation"), inquiry: byType("inquiry"), rule: own.filter(isRule).length };
      const shown = type === "all" ? own : type === "rule" ? own.filter(isRule) : own.filter((item) => !isRule(item) && typeOf(item) === (type === "consultation" ? "consult" : type));
      /* 서버가 주는 상태별 숫자는 원장 보고 카드를 포함한다. 교사 목록과 맞도록 다른 상태도 같은 기준으로 다시 센다 */
      const others = await Promise.all(
        ALL_FILTERS.filter((f) => f !== filter).map((f) =>
          api<CardList>(`/api/v1/cards?filter=${UI_TO_API_FILTER[f]}&size=100`)
            .then((r) => [f, r.items.filter((item) => item.kind !== "director_report").length] as const)
            .catch(() => [f, counts[f]] as const),
        ),
      );
      return { items: shown.map((item) => cardFromItem(item, filter)), counts: { ...counts, ...Object.fromEntries(others), [filter]: own.length } as Record<InboxFilter, number>, typeCounts: recount };
    },
  });
};

/** 모든 상태의 카드를 한 줄로 합친다 (알림의 요청 ID로 카드를 찾을 때 쓴다). 상태별 목록 캐시를 그대로 같이 쓴다. */
const ALL_FILTERS: InboxFilter[] = ["review", "judge", "unassigned", "hold", "progress", "done"];
export const useAllCards = () => {
  const results = useQueries({
    queries: ALL_FILTERS.map((filter) => ({
      queryKey: ["cards", "list", filter, "flat"],
      queryFn: async () => (await api<CardList>(`/api/v1/cards?filter=${UI_TO_API_FILTER[filter]}&size=100`)).items.map((item) => cardFromItem(item, filter)),
    })),
  });
  return results.flatMap((r) => r.data ?? []);
};

export const useCard = (id: string | undefined) => {
  useLiveStream(id ? `/api/v1/cards/${id}/stream` : undefined, ["cards", "detail", id]);
  return useQuery({ queryKey: ["cards", "detail", id], queryFn: () => api<CardDetail>(`/api/v1/cards/${id}`).then(cardFromDetail), enabled: !!id });
};
/** 검사 결과 issues는 서버에서 [{field, problem}]로 온다 (field: 출처·날짜·대상·누락·민감정보). 옛 모양(문자열·message·text)도 읽는다. */
function issueText(i: unknown): string {
  if (typeof i === "string") return i;
  const o = (i ?? {}) as { field?: string; problem?: string; message?: string; text?: string };
  const t = o.problem ?? o.message ?? o.text ?? "";
  return t && o.field ? `${o.field}: ${t}` : t;
}

/** 반려 이유 칩 → API 이유 코드 (문서 4.1). 칩에 없는 이유는 other + reason_text */
const REASON_CODE: Record<string, string> = { "개인정보 요청": "privacy", "원 운영 범위 밖": "policy" };
type ActionResponse = { card?: { id?: string; status?: string; version?: number } };

/** 카드 행동을 API 계약의 기능별 엔드포인트와 요청 본문으로 변환한다. */
/** 원장이 카드 담당 교사를 바꾼다(API 19, 문서 3.16). version은 받지 않는다 */
export function useReassign(cardId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { assigneeId: string; reason: string }) => api(`/api/v1/cards/${cardId}/reassign`, { method: "POST", body: JSON.stringify({ assignee_id: v.assigneeId, reason: v.reason }) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cards"] });
      qc.invalidateQueries({ queryKey: ["overview"] });
    },
  });
}

export function useCardAction(id: string, _role: Role) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({ body, card }: { body: CardAction; card: Card; key: string }) => {
      const version = card.version ?? 1;
      if (body.action === "reclassify") return api<ActionResponse>(`/api/v1/cards/${id}/reclassify`, { method: "POST", body: JSON.stringify({ version, risk_level: body.risk, risk_category: body.risk === "urgent" ? body.riskCategory : null, reason: body.reason }) });
      if (body.action === "confirm_slot") return api<ActionResponse>(`/api/v1/cards/${id}/bookings`, { method: "POST", body: JSON.stringify({ version, slot_id: Number(body.slotId) }) });
      if (body.action === "note") return api<ActionResponse>(`/api/v1/cards/${id}/instructions`, { method: "POST", body: JSON.stringify({ version, instruction: body.text }) });
      const decision = body.action === "approve_send" ? (body.draft ? "edit_approve" : "approve") : body.action === "reject" ? "dismiss" : body.action === "reject_time" ? "reject" : body.action;
      const payload: Record<string, unknown> = { version, decision };
      if (body.action === "approve_send" && body.draft) payload.edited_content = { text: body.draft };
      if (body.action === "reject" || body.action === "reject_time") Object.assign(payload, { reason_code: REASON_CODE[body.reason] ?? "other", reason_text: body.reason });
      if (body.action === "hold") Object.assign(payload, { reason_text: body.reason, hold_until: body.until });
      if (body.action === "complete" && body.reason) payload.reason_text = body.reason;
      return api<ActionResponse>(`/api/v1/cards/${id}/decisions`, { method: "POST", body: JSON.stringify(payload) });
    },
    onSuccess: async () => {
      await Promise.all([qc.invalidateQueries({ queryKey: ["cards", "detail", id] }), qc.invalidateQueries({ queryKey: ["cards", "list"] })]);
    },
  });
}

export const newKey = () => uuid();
