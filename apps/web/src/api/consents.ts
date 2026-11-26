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
