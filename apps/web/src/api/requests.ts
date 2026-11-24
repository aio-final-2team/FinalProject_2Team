import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, uuid } from "./client";

/** 학부모 요청 (API 3·4·5·7, 3.1·3.2·3.9·3.10) */
export type RequestType = "inquiry" | "consultation" | "complaint" | "medication" | "pickup";
/** 투약·귀가 구조화 입력 (문서 3.27). 빠진 칸은 막지 않고 선생님이 다시 물어본다 */
export type CareInput = { medication_name?: string; medication_dose?: string; medication_time?: string; pickup_name?: string; pickup_relation?: string };
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
export type RequestDetail = {
  request: RequestSummary & { body?: string; missing_fields: string[]; parent_confirmed_at: string | null; created_at: string };
  messages: { id: number; sender_type: "user" | "agent" | "system"; sender_role?: "parent" | "teacher" | "director" | null; body: string; created_at: string }[];
  timeline: { label: string; at: string }[];
  consultation?: { slots: { id: number; period: { start: string; end: string }; room: string; status: string }[]; booking: unknown };
  sources?: { document_title: string; location: string | null; effective_from: string | null }[];
  rejection?: { reason_code: string; reason_text: string } | null;
  /** 투약·귀가 요청일 때만 있다 */
  care?: CareView | null;
};

export const TYPE_LABEL: Record<string, string> = { inquiry: "문의", consultation: "상담", complaint: "민원", medication: "투약", pickup: "귀가" };

export const useMyRequests = () => useQuery({ queryKey: ["my-requests"], queryFn: () => api<{ items: RequestSummary[]; total: number }>("/api/v1/requests?size=50") });

export const useRequest = (id?: string) =>
  useQuery({ queryKey: ["request", id], queryFn: () => api<RequestDetail>(`/api/v1/requests/${id}`), enabled: !!id, refetchInterval: 5000 });

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
