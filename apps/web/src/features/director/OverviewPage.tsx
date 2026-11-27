import { useState } from "react";
import { Link } from "react-router";
import { UploadSheet } from "@/features/teacher/UploadSheet";
import { useCareRequests } from "@/api/care";
import { useOverview } from "@/api/overview";
import { Icon } from "@/components/Icon";
import { QueryState } from "@/components/QueryState";
import { ScreenTop } from "@/components/ScreenTop";
import { StateView } from "@/components/StateView";
import { fmtDateTime } from "@/domain/datetime";
import { dateLabel, todayKST } from "@/domain/notes";

const when = fmtDateTime;

/** 원장 현황 (API 21). 숫자를 누르면 받은함의 해당 목록으로 간다. 반별 알림장 현황은 API가 없어 준비 중 칸으로 둔다 */
export function OverviewPage() {
  const q = useOverview();
  const [up, setUp] = useState(false);
  const care = useCareRequests(undefined, true);
  const o = q.data;
  const careOpen = (care.data ?? []).filter((c) => c.status !== "completed").length;

  const tiles: { label: string; n: number; to: string; alert?: boolean }[] = o
    ? [
        { label: "미배정", n: o.unassigned, to: "/director/inbox?filter=unassigned" },
        { label: "대기 중", n: o.waiting, to: "/director/inbox?filter=review" },
        { label: "처리 기한 지남", n: o.delayed, to: "/director/inbox?filter=review", alert: o.delayed > 0 },
        { label: "오늘 닫은 카드", n: o.done_today, to: "/director/inbox?filter=done" },
      ]
    : [];

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop title="현황" sub={`원 전체 · ${dateLabel(todayKST())}`} />
      <QueryState queries={[q]} skeleton={3} errorTitle="현황을 불러오지 못했어요">
        {o && (
          <>
            <ul className="mt-4 grid grid-cols-2 gap-2">
              {tiles.map((t) => (
                <li key={t.label}>
                  <Link to={t.to} className={`block rounded-lg p-3 active:scale-[.98] ${t.alert ? "bg-ink text-card" : "bg-card shadow-card"}`}>
                    <span className={`text-footnote font-semibold ${t.alert ? "opacity-90" : "text-ink2"}`}>{t.label}</span>
                    <b className="mt-1 block text-[32px] font-bold leading-none tabular-nums">{t.n}</b>
                  </Link>
                </li>
              ))}
            </ul>

            <section className="mt-3 rounded-lg bg-card p-3 shadow-card">
              <div className="flex items-center gap-3">
                <span className="grid size-10 shrink-0 place-items-center rounded-md bg-tint text-accent-ink"><Icon name="document" className="size-5" /></span>
                <span className="min-w-0 flex-1">
                  <b className="block text-headline">학부모가 아직 확인하지 않은 완료 {o.completed_unconfirmed}건</b>
                  <span className="text-footnote text-ink2">최근 30일 동안 끝낸 요청이에요</span>
                </span>
              </div>
            </section>

            <button type="button" onClick={() => setUp(true)} className="mt-3 flex w-full items-center gap-3 rounded-lg bg-card p-3 text-left shadow-card active:scale-[.99]">
              <span className="grid size-10 shrink-0 place-items-center rounded-md bg-tint text-accent-ink"><Icon name="document" className="size-5" /></span>
              <span className="min-w-0 flex-1">
                <b className="block text-headline">자료 올리기</b>
                <span className="text-footnote text-ink2">통신문, 식단표, 일정, 운영 규정을 원 전체에 올려요</span>
              </span>
              <Icon name="chevR" className="size-4 shrink-0 text-ink2" />
            </button>
            <UploadSheet open={up} onClose={() => setUp(false)} />

            <Link to="/director/care" className="mt-3 flex items-center gap-3 rounded-lg bg-card p-3 shadow-card active:scale-[.99]">
              <span className="grid size-10 shrink-0 place-items-center rounded-md bg-tint text-accent-ink"><Icon name="medication" className="size-5" /></span>
              <span className="min-w-0 flex-1">
                <b className="block text-headline">귀가·투약 대기 {careOpen}건</b>
                <span className="text-footnote text-ink2">담임이 확인하고 완료하는 요청이에요</span>
              </span>
              <Icon name="chevR" className="size-4 shrink-0 text-ink2" />
            </Link>

            <h2 className="mb-2 mt-6 px-1 text-footnote font-semibold text-ink2">담당 다시 정하기 기록</h2>
            {o.reassignments.length ? (
              <ul className="overflow-hidden rounded-lg bg-card shadow-card [&>li+li]:border-t [&>li+li]:border-sep">
                {o.reassignments.map((r, i) => (
                  <li key={i} className="px-3 py-3">
                    <b className="block text-callout">{r.reason}</b>
                    <span className="text-caption text-ink2">{when(r.at)}</span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-lg bg-card p-4 text-center text-callout text-ink2 shadow-card">아직 담당을 바꾼 기록이 없어요</p>
            )}

            <h2 className="mb-2 mt-6 px-1 text-footnote font-semibold text-ink2">AI 평가 결과</h2>
            {o.eval.length ? (
              <ul className="overflow-hidden rounded-lg bg-card shadow-card [&>li+li]:border-t [&>li+li]:border-sep">
                {o.eval.map((e, i) => (
                  <li key={i} className="flex items-center justify-between gap-3 px-3 py-3">
                    <span className="min-w-0"><b className="block truncate text-callout">{e.suite}</b><span className="text-caption text-ink2">{when(e.started_at)}</span></span>
                    <b className="shrink-0 text-callout tabular-nums">{e.passed}/{e.total}</b>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="rounded-lg bg-card p-4 text-center text-callout text-ink2 shadow-card">아직 평가 결과가 없어요</p>
            )}

            <section aria-label="반별 알림장 현황" className="mt-6 rounded-lg border-[1.5px] border-dashed border-line bg-card p-4">
              <StateView kind="empty" audience="staff" title="반별 알림장 현황은 준비 중이에요" />
            </section>
          </>
        )}
      </QueryState>
    </div>
  );
}
