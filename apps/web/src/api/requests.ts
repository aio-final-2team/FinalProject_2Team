import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, uuid } from "./client";
import { useLiveStream } from "./stream";

/** 학부모 요청 (API 3·4·5·7, 3.1·3.2·3.9·3.10) */
export type RequestType = "inquiry" | "consultation" | "complaint" | "medication" | "pickup";
/** 투약·귀가 구조화 입력 (문서 3.27). 빠진 칸은 막지 않고 선생님이 다시 물어본다 */
export type CareInput = { medication_name?: string; medication_dose?: string; medication_time?: string; pickup_name?: string; pickup_relation?: string; pickup_guardian_id?: string };

/** 등록된 인계자 목록 (API 34): 그 아이에 연결된 보호자 계정. 연락처는 오지 않는다 */
export const usePickupGuardians = (childId?: string) =>
  useQuery({ queryKey: ["pickup-guardians", childId], enabled: !!childId, queryFn: () => api<{ items: { id: string; display_name: string }[] }>(`/api/v1/children/${childId}/pickup-guardians`).then((r) => r.items) });
export type CareView = CareInput & { version: number; unregistered_pickup: boolean; missing_fields: string[]; confirmed_at: string | null; completed_at: string | null };
export type RequestSummary = {
  id: string;
  type: string;
  title: string | null;
  status: string;
  status_label: string;
  updated_at: string;
  next_action: string | null;
  hold_until: string | null;
};
/** 상담 후보 시간. status: proposed(제안) · chosen_by_parent(학부모가 고름) · booked(확정) · discarded(충돌로 버림) */
export type Slot = { id: number; period: { start: string; end: string }; room: string; status: string };
export type RequestDetail = {
  request: RequestSummary & { body?: string; missing_fields: string[]; parent_confirmed_at: string | null; created_at: string };
  messages: { id: number; sender_type: "user" | "agent" | "system"; sender_role?: "parent" | "teacher" | "director" | null; body: string; created_at: string }[];
  timeline: { label: string; at: string }[];
  /** 돌봄 메모 확인 대기(서버 #377). 서버가 아직 안 주면 없다 */
  memory_candidates?: { id: number; child_name: string; content: string }[];
  consultation?: { slots: Slot[]; booking: { id: string; room: string; period: { start: string; end: string } } | null } | null;
  sources?: { document_title: string; location: string | null; effective_from: string | null }[];
  rejection?: { reason_code: string; reason_text: string } | null;
  /** 투약·귀가 요청일 때만 있다 */
  care?: CareView | null;
};

/** 교직원 요청 목록 항목(API GET /requests, 교직원). 서버가 아직 열지 않았으면 빈 목록이다 */
export type StaffRequest = RequestSummary & { child_id: string | null; child_name: string | null; requester_name: string | null; answered_by: "agent" | "staff" | null; classroom_id: string | null };
/** AI가 카드 없이 바로 답하고 끝낸 요청을 교사(우리 반)·원장(원 전체)이 읽는다 */
export const useAiAnswered = (enabled: boolean) =>
  useQuery({
    queryKey: ["ai-answered"],
    enabled,
    retry: false,
    queryFn: async (): Promise<StaffRequest[]> => {
      try {
        return (await api<{ items: StaffRequest[] }>("/api/v1/requests?answered_by=agent&size=50")).items;
      } catch (e) {
        if (e instanceof ApiError && (e.status === 403 || e.status === 422)) return [];
        throw e;
      }
    },
  });

/** 상담 예상 종료 기록 (API 37). 그 반 예약 담임만, 상담이 시작된 뒤에만 */
export type DelayResult = { booking: { id: string; period: { start: string; end: string }; status: string; expected_end_at: string | null }; affected_bookings: number };
export function useConsultDelay(requestId?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { bookingId: string; expectedEndAt: string }) => api<DelayResult>(`/api/v1/consultations/${v.bookingId}/delay`, { method: "POST", body: JSON.stringify({ expected_end_at: v.expectedEndAt }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["request", requestId] }),
  });
}

export const TYPE_LABEL: Record<string, string> = { inquiry: "문의", consultation: "상담", complaint: "민원", medication: "투약", pickup: "귀가" };

export const useMyRequests = () => useQuery({ queryKey: ["my-requests"], queryFn: () => api<{ items: RequestSummary[]; total: number }>("/api/v1/requests?size=50") });

/** live: 학부모 본인 요청 화면에서만 AI 진행 스트림(API 6, 학부모 전용)을 연다 */
export const useRequest = (id?: string, live = false) => {
  useLiveStream(live && id ? `/api/v1/requests/${id}/stream` : undefined, ["request", id]);
  return useQuery({ queryKey: ["request", id], queryFn: () => api<RequestDetail>(`/api/v1/requests/${id}`), enabled: !!id, refetchInterval: 15_000 });
};

export function useCreateRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { type: RequestType; body: string; child_id: string } & CareInput) =>
      api<{ request: { id: string; status: string } }>("/api/v1/requests", {
        method: "POST",
        /* 같은 제출을 두 번 받지 않는 키(client_request_id) */
        body: JSON.stringify({ client_request_id: uuid(), previous_request_id: null, ...b }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["my-requests"] }),
  });
}

export function usePostMessage(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: string) => api(`/api/v1/requests/${id}/messages`, { method: "POST", body: JSON.stringify({ body }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["request", id] }),
  });
}

/** 민원 회신 '확인했어요' (API 9, 3.5) */
export function useConfirmRequest(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api(`/api/v1/requests/${id}/confirm`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["request", id] });
      qc.invalidateQueries({ queryKey: ["my-requests"] });
    },
  });
}

/** 투약·귀가 요청 취소 (API 50). 끝났거나 반려된 요청은 409 */
export function useCancelRequest(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api(`/api/v1/requests/${id}/cancel`, { method: "POST" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["request", id] });
      qc.invalidateQueries({ queryKey: ["my-requests"] });
    },
  });
}

/** 투약·귀가 입력 수정 (API 51). 고치면 선생님이 다시 확인한다 */
export function usePatchCare(id: string) {
  const qc = useQueryClient();
  return useMutation({
    /* version은 상세 care.version(입력 판). 생략한 칸은 그대로 두고 null을 보내면 비운다 */
    mutationFn: (b: { version: number } & { [K in keyof CareInput]?: string | null }) => api(`/api/v1/requests/${id}/care`, { method: "PATCH", body: JSON.stringify(b) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["request", id] });
      qc.invalidateQueries({ queryKey: ["my-requests"] });
    },
  });
}

/** 상담 가능한 시간 체크 (API 8, 문서 3.4). 후보 1~3개를 고르거나, 맞는 시간이 없으면 원하는 시간을 적어 후보를 다시 받는다 */
export function useChooseSlots(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { slot_ids: number[] } | { none_fit: true; preferred_times: string }) => api(`/api/v1/requests/${id}/slot-choices`, { method: "POST", body: JSON.stringify(b) }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ["request", id] });
      qc.invalidateQueries({ queryKey: ["my-requests"] });
    },
  });
}

/** 2026-11-26 09:00 → 11월 26일(목) 오전 9:00 ~ 9:30 */
export function slotLabel(p: { start: string; end: string }) {
  const a = new Date(p.start);
  const b = new Date(p.end);
  const day = a.toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short" });
  const t = (d: Date) => d.toLocaleTimeString("ko-KR", { hour: "numeric", minute: "2-digit", hour12: true });
  return `${day} ${t(a)} ~ ${t(b)}`;
}
