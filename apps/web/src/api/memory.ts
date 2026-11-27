import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

/**
 * 내 AI 기억 (API 31·삭제, 문서 3.25)과 개인 규칙 제안 결정 (API 20, 문서 3.17).
 * 서버 #377부터 세 역할이 쓴다. 새 칸(title·child_name·confirm_status·source)은 서버가 주기 전까지 없을 수 있다.
 * source가 memory(또는 없음)이면 id는 숫자, saved_answer·rule이면 uuid 문자열이다.
 */
export type MemoryKind = "rejection_reason" | "preference" | "tone" | "care_note" | "saved_answer" | "rule";
export type Memory = {
  id: number | string; kind: MemoryKind; reason_code: string | null; content: string; structured: Record<string, unknown>; created_at: string;
  title?: string; child_id?: string | null; child_name?: string | null;
  confirm_status?: "pending" | "confirmed" | "discarded" | null; confirmed_at?: string | null;
  source?: "memory" | "saved_answer" | "rule";
};

export const KIND_LABEL: Record<MemoryKind, string> = { rejection_reason: "거절한 이유", preference: "선호", tone: "말투", care_note: "돌봄 메모", saved_answer: "승인한 답", rule: "규칙" };
/** source=memory만 삭제한다. 구버전 서버는 source가 없으므로 숫자 id를 기억으로 본다. */
export const isDeletable = (m: Memory) => m.source === "memory" || (!m.source && typeof m.id === "number");
/** 승인한 답·규칙의 상태(structured.status) */
export const statusOf = (m: Memory) => (typeof m.structured?.status === "string" ? (m.structured.status as string) : undefined);
/** 반려 이유 코드 → 담임이 읽는 말 (문서 4.1) */
export const REASON_LABEL: Record<string, string> = { wrong_fact: "사실이 달라요", tone: "말투가 맞지 않아요", missing_info: "정보가 부족해요", privacy: "개인정보 요청", policy: "원 운영 범위 밖", slot_unavailable: "상담 가능한 시간이 아니에요", room_unavailable: "상담실을 쓸 수 없어요", other: "그 밖의 이유" };

export const useMemories = () => useQuery({ queryKey: ["memories"], queryFn: () => api<{ items: Memory[]; total: number }>("/api/v1/memories?size=100").then((r) => r.items) });

export function useDeleteMemory() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (id: number) => api<void>(`/api/v1/memories/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["memories"] }) });
}

/** 돌봄 메모 확인 (API 67): 그 아이 보호자만, 대기 중인 것만. 기억하기 remember · 기억하지 않기 discard */
export function useConfirmMemory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: number; decision: "remember" | "discard" }) => api<{ id: number; confirm_status: string }>(`/api/v1/memories/${v.id}/confirm`, { method: "POST", body: JSON.stringify({ decision: v.decision }) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["memories"] });
      qc.invalidateQueries({ queryKey: ["request"] });
    },
  });
}

/** 승인한 답 끄기·켜기 (API 69). 끄면 AI가 다시 쓰지 않는다 */
export function useSavedAnswerStatus() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; status: "off" | "active" }) => api<{ id: string; status: string }>(`/api/v1/saved-answers/${v.id}`, { method: "PATCH", body: JSON.stringify({ status: v.status }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories"] }),
  });
}

/** 규칙 제안 카드의 켜기·거절, 기억 화면의 활성 규칙 끄기 (API 20) */
export function useRuleDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { ruleId: string; decision: "activate" | "decline" | "off" }) => api<{ rule: { id: string; status: string } }>(`/api/v1/memory-rules/${v.ruleId}/decision`, { method: "POST", body: JSON.stringify({ decision: v.decision }) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cards"] });
      qc.invalidateQueries({ queryKey: ["memories"] });
    },
  });
}
