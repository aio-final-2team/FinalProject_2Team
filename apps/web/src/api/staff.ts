import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

/** 한국 시간(KST) 기준 날짜 도우미. 서버 날짜·시간이 모두 KST라서 브라우저 시간대와 무관하게 맞춘다 */
const DAY = 86_400_000;
export const kstDate = (offsetDays = 0): string => new Date(Date.now() + 9 * 3_600_000 + offsetDays * DAY).toISOString().slice(0, 10);
export const kstIso = (date: string, hm: string): string => `${date}T${hm}:00+09:00`;
export const kstDay = (iso: string): string => new Date(new Date(iso).getTime() + 9 * 3_600_000).toISOString().slice(0, 10);
export const kstHm = (iso: string): string => new Date(new Date(iso).getTime() + 9 * 3_600_000).toISOString().slice(11, 16);

/** 원 일정. 기간 안의 일정을 날짜순으로 준다 */
export type CalendarItem = { date: string; end_date: string | null; title: string; document_id: string; document_title: string; location: string };
export const useCalendar = (from: string, to: string) =>
  useQuery({
    queryKey: ["calendar", from, to],
    queryFn: () => api<{ items: CalendarItem[] }>(`/api/v1/calendar?from=${from}&to=${to}`).then((r) => r.items),
  });

/** 바쁜 시간(상담을 받을 수 없는 시간) 조회·등록·삭제 */
export type BusyKind = "class" | "meeting" | "duty" | "off" | "other";
export type BusyBlock = { id: number; user_id: string; start_at: string; end_at: string; kind: BusyKind };
export const BUSY_LABEL: Record<BusyKind, string> = { class: "수업", meeting: "회의", duty: "당번", off: "쉬는 날", other: "기타" };

export const useBusyBlocks = (fromDate: string, toDate: string) =>
  useQuery({
    queryKey: ["busy-blocks", fromDate, toDate],
    queryFn: () => api<{ items: BusyBlock[] }>(`/api/v1/staff/busy-blocks?from=${encodeURIComponent(kstIso(fromDate, "00:00"))}&to=${encodeURIComponent(kstIso(toDate, "23:59"))}`).then((r) => r.items),
  });

export function useCreateBusyBlock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (b: { date: string; start: string; end: string; kind: BusyKind }) =>
      api<BusyBlock>("/api/v1/staff/busy-blocks", { method: "POST", body: JSON.stringify({ start_at: kstIso(b.date, b.start), end_at: kstIso(b.date, b.end), kind: b.kind }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["busy-blocks"] }),
  });
}

export function useDeleteBusyBlock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api<void>(`/api/v1/staff/busy-blocks/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["busy-blocks"] }),
  });
}

/** 알림 조용한 시간 (API 64·65). 두 칸 모두 HH:MM이거나 둘 다 null이다 */
export type NotificationSettings = { quiet_start: string | null; quiet_end: string | null };
export const useNotificationSettings = () => useQuery({ queryKey: ["notification-settings"], queryFn: () => api<NotificationSettings>("/api/v1/me/notification-settings") });

export function useSaveNotificationSettings() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (s: NotificationSettings) => api<NotificationSettings>("/api/v1/me/notification-settings", { method: "PATCH", body: JSON.stringify(s) }),
    onSuccess: (s) => qc.setQueryData(["notification-settings"], s),
  });
}

/** 교직원 AI에게 묻기. 원 자료를 근거로 답하고, 근거 문서가 서로 다르면 conflict가 true다 */
export type StaffEvidence = { document_id: string; title: string; location: string; effective_date: string | null };
export type StaffAnswer = { answer: string; evidence: StaffEvidence[]; conflict?: boolean };
export const useStaffAsk = () => useMutation({ mutationFn: (question: string) => api<StaffAnswer>("/api/v1/staff/ask", { method: "POST", body: JSON.stringify({ question }) }) });

/** 재배정할 선생님 목록(원장 전용). 아직 맡은 카드가 없는 선생님과 반이 없는 보조 교사도 나온다 */
export type TeacherItem = { id: string; display_name: string; classrooms: { id: string; name: string }[] };
export const useTeachers = (enabled = true) => useQuery({ queryKey: ["staff", "teachers"], enabled, queryFn: () => api<{ items: TeacherItem[] }>("/api/v1/staff/teachers").then((r) => r.items), staleTime: 60_000 });
