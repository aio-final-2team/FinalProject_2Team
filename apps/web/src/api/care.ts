import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { RequestIntent } from "@/domain/status";
import { api } from "./client";

/**
 * 투약·귀가 요청 (API 35·36, 문서 3.27).
 * 목록에는 아이 이름이 없어 요청 문장(title)으로 보여 준다. 이름이 내려오면 이 타입에 칸만 더하면 된다.
 */
export type CareType = "medication" | "pickup";
export type CareStatus = "received" | "assigned" | "completed" | "rejected";
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
  /** 완료 때 남긴 처리 결과 한 줄. 그날 알림장 입력의 이 요청 자리에 들어간다 */
  result_line?: string | null;
  /** 투약·귀가는 늘 ask(부탁) */
  intent?: RequestIntent | null;
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
    /* reject는 사유(reason_text 1~1000자)가 필요하고, 사유는 보호자에게 전달된다 */
    /* result_line은 완료 때만 보내는 선택 칸. 비우면 서버가 '13시에 약 먹였어요'처럼 처리 시각으로 만든다 */
    mutationFn: async (v: { id: string; decision: "confirm" | "complete" | "reject"; version: number; reason_text?: string; result_line?: string; type?: CareType }) => {
      /* 등록된 인계자로 접수된 귀가 요청은 confirm·complete에 같은 pickup_guardian_id를 다시 보낸다(문서 3.27). 미등록이면 생략한다 */
      let guardian: string | undefined;
      if (v.type === "pickup" && v.decision !== "reject") {
        const d = await api<{ care?: { pickup_guardian_id?: string | null } | null }>(`/api/v1/requests/${v.id}`).catch(() => null);
        guardian = d?.care?.pickup_guardian_id ?? undefined;
      }
      return api(`/api/v1/requests/${v.id}/care-decisions`, { method: "POST", body: JSON.stringify({ decision: v.decision, version: v.version, ...(guardian ? { pickup_guardian_id: guardian } : {}), ...(v.reason_text ? { reason_text: v.reason_text } : {}), ...(v.decision === "complete" && v.result_line?.trim() ? { result_line: v.result_line.trim() } : {}) }) });
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["care-requests"] }),
  });
}
