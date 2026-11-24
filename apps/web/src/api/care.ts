import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

/**
 * 투약·귀가 요청 (API 35·36, 문서 3.27).
 * 목록에는 아이 이름이 없어 요청 문장(title)으로 보여 준다. 이름이 내려오면 이 타입에 칸만 더하면 된다.
 */
export type CareType = "medication" | "pickup";
export type CareStatus = "received" | "assigned" | "completed";
export type CareItem = {
  id: string;
  type: CareType;
  title: string;
  status: CareStatus;
  status_label: string;
  updated_at: string;
  next_action: "confirm" | "complete" | null;
  version: number;
  unregistered_pickup: boolean;
  missing_fields: string[];
  /** 태웅님이 11/24에 추가하기로 한 칸. 서버에 올라오기 전에는 없다 */
  child_id?: string;
  child_name?: string;
};

export const MISSING_LABEL: Record<string, string> = { medication_name: "약 이름", medication_dose: "용량", medication_time: "먹일 시간" };

/** all: 원장처럼 반을 정하지 않고 원 전체를 볼 때 */
export function useCareRequests(classroomId?: string, all = false) {
  return useQuery({
    queryKey: ["care-requests", classroomId],
    queryFn: () => api<{ items: CareItem[]; total: number }>(`/api/v1/care-requests?size=100&sort=-created_at${classroomId ? `&classroom_id=${classroomId}` : ""}`).then((r) => r.items),
    enabled: all || !!classroomId,
  });
}

/** confirm = 내용을 확인했다, complete = 실제로 투약·인계를 마쳤다 */
export function useCareDecision() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { id: string; decision: "confirm" | "complete"; version: number }) =>
      api(`/api/v1/requests/${v.id}/care-decisions`, { method: "POST", body: JSON.stringify({ decision: v.decision, version: v.version }) }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["care-requests"] }),
  });
}
