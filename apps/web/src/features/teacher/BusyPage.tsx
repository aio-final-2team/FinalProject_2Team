import { useState } from "react";
import { ApiError } from "@/api/client";
import { BUSY_LABEL, kstDate, kstDay, kstHm, useBusyBlocks, useCreateBusyBlock, useDeleteBusyBlock, type BusyBlock, type BusyKind } from "@/api/staff";
import { Button } from "@/components/Button";
import { QueryState } from "@/components/QueryState";
import { ScreenTop } from "@/components/ScreenTop";
import { StateView } from "@/components/StateView";
import { useToast } from "@/components/Toast";
import { dateLabel } from "@/domain/notes";

const DAYS = 30;
const KINDS = Object.keys(BUSY_LABEL) as BusyKind[];
const field = "h-12 w-full rounded-md border-[1.5px] border-line bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]";

/** 바쁜 시간 관리. 이 시간에는 상담 시간으로 잡히지 않는다. 오늘부터 30일 동안 보고 등록·삭제한다 */
export function BusyPage() {
  const today = kstDate();
  const q = useBusyBlocks(today, kstDate(DAYS));
  const create = useCreateBusyBlock();
  const remove = useDeleteBusyBlock();
  const toast = useToast();
  const [date, setDate] = useState(today);
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("10:00");
  const [kind, setKind] = useState<BusyKind>("meeting");
  const invalid = !date || !start || !end || end <= start;

  const days = new Map<string, BusyBlock[]>();
  [...(q.data ?? [])].sort((a, b) => a.start_at.localeCompare(b.start_at)).forEach((b) => days.set(kstDay(b.start_at), [...(days.get(kstDay(b.start_at)) ?? []), b]));

  const save = () => {
    if (invalid) return;
    create.mutate(
      { date, start, end, kind },
      {
        onSuccess: () => toast({ kind: "ok", title: "바쁜 시간을 등록했어요" }),
        onError: (e) => {
          if (e instanceof ApiError && e.status === 409) toast({ kind: "error", title: "겹치는 바쁜 시간이 있어요", sub: "시간을 바꿔서 다시 등록해 주세요" });
          else if (e instanceof ApiError && e.status === 422) toast({ kind: "error", title: "시간을 확인해 주세요", sub: "끝나는 시간이 시작 시간보다 늦어야 해요" });
          else toast({ kind: "error", title: "등록하지 못했어요", sub: "연결을 확인하고 다시 눌러 주세요" });
        },
      },
    );
  };
  const del = (b: BusyBlock) =>
    remove.mutate(b.id, {
      onSuccess: () => toast({ kind: "ok", title: "바쁜 시간을 지웠어요" }),
      onError: (e) => toast({ kind: "error", title: e instanceof ApiError && e.status === 404 ? "이미 지워진 시간이에요" : "지우지 못했어요", sub: e instanceof ApiError && e.status === 404 ? undefined : "연결을 확인하고 다시 눌러 주세요" }),
    });

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop back={{ to: "/teacher/home", label: "홈" }} title="바쁜 시간" sub="이 시간에는 학부모 상담이 잡히지 않아요" />

      <section className="mt-5 grid gap-3 rounded-lg bg-card p-4 shadow-card" aria-label="바쁜 시간 등록">
        <label className="grid gap-1.5">
          <span className="px-1 text-footnote font-semibold text-ink2">날짜</span>
          <input type="date" value={date} min={today} onChange={(e) => setDate(e.target.value)} className={field} />
        </label>
        <div className="grid grid-cols-2 gap-3">
          <label className="grid gap-1.5">
            <span className="px-1 text-footnote font-semibold text-ink2">시작</span>
            <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className={field} />
          </label>
          <label className="grid gap-1.5">
            <span className="px-1 text-footnote font-semibold text-ink2">끝</span>
            <input type="time" value={end} onChange={(e) => setEnd(e.target.value)} className={field} />
          </label>
        </div>
        <div role="group" aria-label="종류" className="flex flex-wrap gap-2">
          {KINDS.map((k) => (
            <button
              key={k}
              type="button"
              aria-pressed={kind === k}
              onClick={() => setKind(k)}
              className={`h-9 rounded-full border px-3 text-footnote font-semibold transition-colors ${kind === k ? "border-accent bg-tint text-accent-ink" : "border-sep bg-card text-ink"}`}
            >
              {BUSY_LABEL[k]}
            </button>
          ))}
        </div>
        {end <= start && start && end && <p role="alert" className="px-1 text-caption text-danger">끝나는 시간이 시작 시간보다 늦어야 해요</p>}
        <Button loading={create.isPending} disabled={invalid} onClick={save} className="w-full">등록</Button>
      </section>

      <QueryState queries={[q]} skeleton={2} errorTitle="바쁜 시간을 불러오지 못했어요">
        {days.size === 0 ? (
          <div className="mt-6">
            <StateView kind="empty" audience="staff" title="등록한 바쁜 시간이 없어요" sub={"수업이나 회의처럼 상담을 받을 수 없는\n시간을 등록해 두세요"} />
          </div>
        ) : (
          [...days].map(([d, items]) => (
            <section key={d} className="mt-5" aria-label={dateLabel(d)}>
              <h2 className="mb-2 px-1 text-footnote font-semibold text-ink2">{dateLabel(d)}</h2>
              <ul className="overflow-hidden rounded-lg bg-card shadow-card [&>li+li]:border-t [&>li+li]:border-sep">
                {items.map((b) => (
                  <li key={b.id} className="flex items-center gap-3 px-3 py-3">
                    <span className="min-w-0 flex-1">
                      <b className="block text-callout font-semibold tabular-nums">{kstHm(b.start_at)} ~ {kstHm(b.end_at)}</b>
                      <span className="block text-footnote text-ink2">{BUSY_LABEL[b.kind]}</span>
                    </span>
                    <button type="button" disabled={remove.isPending} onClick={() => del(b)} aria-label={`${kstHm(b.start_at)} 바쁜 시간 지우기`} className="h-9 shrink-0 rounded-md px-2.5 text-footnote font-semibold text-ink2 active:scale-[.97] disabled:opacity-50">지우기</button>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </QueryState>
    </div>
  );
}
