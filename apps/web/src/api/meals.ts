import { useQueries } from "@tanstack/react-query";
import { api } from "./client";
import { useDocuments, type Doc } from "./documents";

/** 식단표 자료(API 29)의 본문 표에서 날짜별 점심·오후 간식을 읽는다. 표 모양: | 11-30(월) | 점심 | 간식 | */
export type MealDay = { date: string; label: string; lunch: string; snack: string };

const DAY = ["일", "월", "화", "수", "목", "금", "토"];
/** 마크다운 강조(**)와 겹친 공백을 걷어 낸다 */
export const plain = (s: string) => s.replace(/\*\*/g, "").replace(/\s+/g, " ").trim();

const addDays = (iso: string, n: number) => {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
};

export function parseMenu(content: string, year: number): MealDay[] {
  const out: MealDay[] = [];
  for (const line of content.split("\n")) {
    const m = line.match(/^\|\s*(\d{2})-(\d{2})\([월화수목금토일]\)\s*\|(.+)\|(.*)\|\s*$/);
    if (!m) continue;
    const date = `${year}-${m[1]}-${m[2]}`;
    const dow = DAY[new Date(`${date}T00:00:00Z`).getUTCDay()];
    out.push({ date, label: `${Number(m[1])}/${Number(m[2])}(${dow})`, lunch: plain(m[3]), snack: plain(m[4]) });
  }
  return out;
}

/**
 * 오늘 식단, 없으면 가장 가까이 돌아오는 날짜의 식단.
 * 오늘 기준 앞 7일~뒤 14일에 시작한 적용 중인 식단표만 읽는다.
 */
export function useNextMeal(today: string) {
  const docs = useDocuments();
  const picked = (docs.data ?? []).filter((d) => d.doc_type === "menu" && d.status === "active" && d.title.includes("식단표") && !d.title.startsWith("가상") && d.effective_from >= addDays(today, -7) && d.effective_from <= addDays(today, 14));
  const details = useQueries({
    queries: picked.map((d) => ({ queryKey: ["document", d.id], queryFn: () => api<{ document: Doc }>(`/api/v1/documents/${d.id}`).then((r) => r.document), staleTime: 5 * 60_000 })),
  });
  const days = details.flatMap((q) => (q.data?.chunks ?? []).flatMap((c) => parseMenu(c.content, Number(q.data!.effective_from.slice(0, 4)))));
  const next = days.filter((d) => d.date >= today).sort((a, b) => a.date.localeCompare(b.date))[0];
  return { data: next ? { ...next, today: next.date === today } : null, isLoading: docs.isLoading || details.some((q) => q.isLoading) };
}

/** 가정통신문 한 줄: 적용 중인 통신문 중 오늘 기준 7일 뒤까지 시작한 것 가운데 가장 최근 것 */
export function pickNotice(docs: Doc[] | undefined, today: string): Doc | undefined {
  return (docs ?? [])
    .filter((d) => d.doc_type === "notice" && d.status === "active" && d.effective_from <= addDays(today, 7) && !d.title.startsWith("가상"))
    .sort((a, b) => b.effective_from.localeCompare(a.effective_from))[0];
}
