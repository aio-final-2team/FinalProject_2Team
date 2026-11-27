import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

/** 필수 동의 (API 53~55 [제안]). 로그인한 사람의 역할별 항목과 동의 시각, 현재 약관 판 */
export type ConsentItem = { item: string; label: string; required: true; agreed_at: string | null };
export type ConsentOut = { terms_version: string; complete: boolean; items: ConsentItem[] };

export const useConsents = () => useQuery({ queryKey: ["consents"], queryFn: () => api<ConsentOut>("/api/v1/consents") });

/** 전 항목에 한 번에 동의한다. 약관 판이 다르면 409 CONSENT_VERSION_MISMATCH, 빠진 항목이 있으면 422 CONSENT_INCOMPLETE */
export function useAgreeConsents() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { items: string[]; terms_version: string }) => api<ConsentOut>("/api/v1/consents", { method: "POST", body: JSON.stringify(v) }),
    onSuccess: (d) => qc.setQueryData(["consents"], d),
  });
}

/** 반 아이별 보호자 동의 현황 (API 55). 같은 원의 원장·현재 그 반 담임만 */
export type ChildConsent = { child_id: string; display_name: string; guardians_total: number; guardians_complete: number; complete: boolean };
export const useClassroomConsents = (classroomId?: string) =>
  useQuery({ queryKey: ["consents", "classroom", classroomId], enabled: !!classroomId, queryFn: () => api<{ items: ChildConsent[] }>(`/api/v1/classrooms/${classroomId}/consents`).then((r) => r.items) });
