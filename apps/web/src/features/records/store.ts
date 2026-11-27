import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import { kstHm } from "@/api/staff";
import { useToast } from "@/components/Toast";

/**
 * 하루 중 기록 (A안 '오늘 기록'). 서버에 저장하므로 다른 기기와 브라우저에서도 이어진다.
 * 아이별로 모아 알림장 초안을 만들 때 API 22의 child_memos로 보낸다.
 */
export type RecordEntry = { id: string; at: string; text: string };
export type Records = Record<string, RecordEntry[]>; // child_id → 기록

type RecordRow = { id: string; child_id: string; body: string; note_date: string; created_at: string };
const EMPTY: Records = {};

export function useRecords(cid: string | undefined, date: string) {
  const qc = useQueryClient();
  const toast = useToast();
  const key = ["records", cid, date];
  const q = useQuery({
    queryKey: key,
    enabled: !!cid,
    queryFn: () => api<{ items: RecordRow[] }>(`/api/v1/classrooms/${cid}/records?date=${date}`).then((r) => r.items),
    /* 같은 값이면 같은 객체를 돌려줘서 화면이 쓸데없이 다시 그려지지 않게 한다 */
    select: (rows): Records => {
      const out: Records = {};
      [...rows]
        .sort((a, b) => a.created_at.localeCompare(b.created_at))
        .forEach((r) => (out[r.child_id] ??= []).push({ id: r.id, at: kstHm(r.created_at), text: r.body }));
      return out;
    },
  });
  const records = q.data ?? EMPTY;
  const failed = (title: string) => toast({ kind: "error", title, sub: "연결을 확인하고 다시 눌러 주세요" });
  const done = () => qc.invalidateQueries({ queryKey: key });

  const addM = useMutation({
    mutationFn: (v: { childId: string; text: string }) => api(`/api/v1/classrooms/${cid}/records`, { method: "POST", body: JSON.stringify({ child_id: v.childId, body: v.text.slice(0, 500), note_date: date }) }),
    onSuccess: done,
    onError: () => failed("기록을 저장하지 못했어요"),
  });
  const removeM = useMutation({
    mutationFn: (id: string) => api<void>(`/api/v1/records/${id}`, { method: "DELETE" }),
    onSuccess: done,
    onError: () => failed("기록을 지우지 못했어요"),
  });

  const add = (childId: string, text: string) => addM.mutate({ childId, text });
  /** 기록 한 줄 삭제 */
  const remove = (childId: string, index: number) => {
    const row = records[childId]?.[index];
    if (row) removeM.mutate(row.id);
  };
  /** 아이별 기록을 한 줄 메모로 합친다 (child_memos 1~500자) */
  const memoOf = (childId: string) =>
    (records[childId] ?? [])
      .map((r) => r.text)
      .join(", ")
      .slice(0, 500);
  return { records, add, remove, memoOf, query: q };
}
