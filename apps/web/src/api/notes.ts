import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Child, DailyNote, DraftJob, NoteItem } from "@/domain/notes";
import { api } from "./client";

type Page<T> = { items: T[]; total: number; page: number; size: number };

/** API 30: 반 아이 목록(이름순) */
export const useChildren = (classroomId?: string) =>
  useQuery({
    queryKey: ["children", classroomId],
    queryFn: () => api<{ items: Child[] }>(`/api/v1/classrooms/${classroomId}/children`).then((r) => r.items),
    enabled: !!classroomId,
    staleTime: 5 * 60_000,
  });

/** API 24: 날짜별 아이 알림장 (담임은 classroom_id 필수) */
export const useNotes = (classroomId?: string, date?: string) =>
  useQuery({
    queryKey: ["notes", classroomId, date],
    queryFn: () =>
      api<Page<DailyNote>>(`/api/v1/daily-notes?classroom_id=${classroomId}&date=${date}&size=100&sort=created_at`).then((r) => r.items),
    enabled: !!classroomId && !!date,
  });

/** API 22: 초안 만들기(202). child_memos는 v0.4에서 더해진 선택 칸 */
export function useCreateDraft() {
  return useMutation({
    mutationFn: (body: { classroom_id: string; note_date: string; activities: string; supplies: string; child_memos?: { child_id: string; memo: string }[] }) =>
      api<DraftJob>("/api/v1/daily-notes/drafts", { method: "POST", body: JSON.stringify(body) }),
  });
}

/** API 23: 진행 상태. 끝날 때까지 0.8초마다 다시 본다 */
export const useDraftJob = (inputId?: string) =>
  useQuery({
    queryKey: ["draft-job", inputId],
    queryFn: () => api<DraftJob>(`/api/v1/daily-notes/drafts/${inputId}`),
    enabled: !!inputId,
    refetchInterval: (q) => (q.state.data && ["succeeded", "failed"].includes(q.state.data.draft_status) ? false : 800),
  });

/** API 25: 고치기·확인. content를 보내면 전체 내용을 바꾼다 */
export function usePatchNote(classroomId?: string, date?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: { content?: { items: NoteItem[] }; resolved_checks?: string[]; confirm?: boolean } }) =>
      api<{ note: DailyNote }>(`/api/v1/daily-notes/${id}`, { method: "PATCH", body: JSON.stringify(body) }).then((r) => r.note),
    onSuccess: (note) => {
      qc.setQueryData<DailyNote[]>(["notes", classroomId, date], (list) => list?.map((n) => (n.id === note.id ? { ...n, ...note } : n)));
    },
  });
}

/** API 26: 반 알림장 한 번에 보내기. 확인 안 된 아이가 있으면 409 NOTE_BATCH_BLOCKED */
export function useSendNotes(classroomId?: string, date?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () =>
      api<{ sent_count: number }>("/api/v1/daily-notes/send", { method: "POST", body: JSON.stringify({ classroom_id: classroomId, note_date: date }) }),
    onSettled: () => qc.invalidateQueries({ queryKey: ["notes", classroomId, date] }),
  });
}

/* ── 입력 ID 기억: 다시 만들기(API 26)가 input_id를 쓴다. 알림장 응답에는 input_id가 없어서 이 기기에 둔다 ── */
const inKey = (cid: string, date: string) => `yuchion.input.${cid}.${date}`;
export function saveInputId(cid: string, date: string, id: string) {
  try {
    localStorage.setItem(inKey(cid, date), id);
  } catch {
    /* 저장이 막히면 다시 만들기 버튼만 숨긴다 */
  }
}
export function loadInputId(cid: string | undefined, date: string): string | null {
  try {
    return cid ? localStorage.getItem(inKey(cid, date)) : null;
  } catch {
    return null;
  }
}

/** API 26(3.26): 저장해 둔 입력으로 아직 확인하지 않은 초안만 다시 만든다. 고친 알림장·확인한 알림장은 보존(kept_edited) */
export function useRegenerate() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (inputId: string) => api<DraftJob & { kept_edited: number }>(`/api/v1/daily-notes/drafts/${inputId}/regenerate`, { method: "POST" }),
    onSuccess: (_r, inputId) => {
      qc.invalidateQueries({ queryKey: ["draft-job", inputId] });
      qc.invalidateQueries({ queryKey: ["notes"] });
    },
  });
}

/** 보낸 알림장 정정 (API 52, 문서 3.30). 내용 전체를 바꾸고 사유(1~500자)와 조회한 판(version)을 보낸다. 학부모에게 정정 알림이 간다 */
export function useCorrectNote(classroomId?: string, date?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, version, items, reason_text }: { id: string; version: number; items: NoteItem[]; reason_text: string }) =>
      api<{ note: DailyNote }>(`/api/v1/daily-notes/${id}/correct`, {
        method: "POST",
        body: JSON.stringify({ version, reason_text, content: { items: items.map(({ key, label, value, source }) => ({ key, label, value, source })) } }),
      }).then((r) => r.note),
    onSuccess: (note) => {
      qc.setQueryData<DailyNote[]>(["notes", classroomId, date], (list) => list?.map((n) => (n.id === note.id ? { ...n, ...note } : n)));
    },
    onSettled: () => qc.invalidateQueries({ queryKey: ["notes", classroomId, date] }),
  });
}
