import { useSyncExternalStore } from "react";

/**
 * 하루 중 기록 (A안 '오늘 기록'). 아직 API가 없어서 이 기기 브라우저에만 모아 두고,
 * 초안을 만들 때 아이별로 합쳐 API 22의 child_memos로 보낸다. 서버 API가 생기면 이 파일만 바꾼다.
 */
export type RecordEntry = { at: string; text: string };
export type Records = Record<string, RecordEntry[]>; // child_id → 기록

const key = (cid: string, date: string) => `yuchion.records.${cid}.${date}`;
const listeners = new Set<() => void>();
const cache = new Map<string, Records>();

function read(k: string): Records {
  if (cache.has(k)) return cache.get(k)!;
  let v: Records = {};
  try {
    v = JSON.parse(localStorage.getItem(k) ?? "{}");
  } catch {
    /* 저장이 막힌 브라우저면 빈 기록으로 시작 */
  }
  cache.set(k, v);
  return v;
}

function write(k: string, v: Records) {
  cache.set(k, v);
  try {
    localStorage.setItem(k, JSON.stringify(v));
  } catch {
    /* 이번 화면에서는 계속 쓸 수 있다 */
  }
  listeners.forEach((l) => l());
}

export function useRecords(cid: string | undefined, date: string) {
  const k = key(cid ?? "-", date);
  const records = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => read(k),
  );
  const add = (childId: string, text: string) => {
    const now = new Date();
    const at = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    const cur = read(k);
    write(k, { ...cur, [childId]: [...(cur[childId] ?? []), { at, text }] });
  };
  /** 기록 한 줄 삭제 (남은 기록이 없으면 그 아이 항목도 지운다) */
  const remove = (childId: string, index: number) => {
    const cur = read(k);
    const left = (cur[childId] ?? []).filter((_, i) => i !== index);
    const next = { ...cur };
    if (left.length) next[childId] = left;
    else delete next[childId];
    write(k, next);
  };
  /** 아이별 기록을 한 줄 메모로 합친다 (child_memos 1~500자) */
  const memoOf = (childId: string) =>
    (records[childId] ?? [])
      .map((r) => r.text)
      .join(", ")
      .slice(0, 500);
  return { records, add, remove, memoOf };
}
