import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, uuid } from "./client";

/** 학부모 요청 (API 3·4·5·7, 3.1·3.2·3.9·3.10) */
export type RequestType = "inquiry" | "consultation" | "complaint";
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
};

export const TYPE_LABEL: Record<string, string> = { inquiry: "문의", consultation: "상담", complaint: "민원", medication: "투약", pickup: "귀가" };

export const useMyRequests = () => useQuery({ queryKey: ["my-requests"], queryFn: () => api<{ items: RequestSummary[]; total: number }>("/api/v1/requests?size=50") });

export const useRequest = (id?: string) =>
  useQuery({ queryKey: ["request", id], queryFn: () => api<RequestDetail>(`/api/v1/requests/${id}`), enabled: !!id, refetchInterval: 5000 });

export function useCreateRequest() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { type: RequestType; body: string; child_id: string }) =>
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
