import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

/** API 11(3.11) 알림 목록·읽음. 알림장 알림은 subject_type = daily_note */
export type Notification = {
  id: number;
  kind: string;
  title: string;
  body: string | null;
  request_id: string | null;
  subject_type: string | null;
  subject_id: string | null;
  read_at: string | null;
  deliver_after: string;
};

export const useNotifications = () =>
  useQuery({
    queryKey: ["notifications"],
    queryFn: () => api<{ items: Notification[]; total: number }>("/api/v1/notifications?size=50"),
    refetchInterval: 20_000,
  });

export function useReadNotification() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<{ notification: Notification }>(`/api/v1/notifications/${id}/read`, { method: "POST" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });
}
