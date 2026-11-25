import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

/** 내 AI 기억 (API 31·삭제, 문서 3.25)과 개인 규칙 제안 결정 (API 20, 문서 3.17). 담임만 쓴다 */
export type MemoryKind = "rejection_reason" | "preference" | "tone";
export type Memory = { id: number; kind: MemoryKind; reason_code: string | null; content: string; structured: Record<string, unknown>; created_at: string };

export const KIND_LABEL: Record<MemoryKind, string> = { rejection_reason: "반려·거절한 이유", preference: "선호", tone: "말투" };
/** 반려 이유 코드 → 담임이 읽는 말 (문서 4.1) */
export const REASON_LABEL: Record<string, string> = { wrong_fact: "사실이 달라요", tone: "말투가 맞지 않아요", missing_info: "정보가 부족해요", privacy: "개인정보 요청", policy: "원 운영 범위 밖", slot_unavailable: "상담 가능한 시간이 아니에요", room_unavailable: "상담실을 쓸 수 없어요", other: "그 밖의 이유" };

export const useMemories = () => useQuery({ queryKey: ["memories"], queryFn: () => api<{ items: Memory[]; total: number }>("/api/v1/memories?size=100").then((r) => r.items) });

export function useDeleteMemory() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (id: number) => api<void>(`/api/v1/memories/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["memories"] }) });
}

/** 규칙 제안 카드의 켜기(activate)·거절(decline) */
export function useRuleDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { ruleId: string; decision: "activate" | "decline" }) => api<{ rule: { id: string; status: string } }>(`/api/v1/memory-rules/${v.ruleId}/decision`, { method: "POST", body: JSON.stringify({ decision: v.decision }) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cards"] });
      qc.invalidateQueries({ queryKey: ["memories"] });
    },
  });
}
