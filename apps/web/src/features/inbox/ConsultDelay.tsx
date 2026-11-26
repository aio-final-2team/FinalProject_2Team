import { useState } from "react";
import { ApiError } from "@/api/client";
import { useConsultDelay, useRequest } from "@/api/requests";
import { Button } from "@/components/Button";
import { Sheet } from "@/components/Sheet";
import { useToast } from "@/components/Toast";

const hm = (d: Date) => d.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });
/** 서버가 받는 시각 모양: 한국 시각 오프셋을 붙인다 */
const kst = (d: Date) => {
  const k = new Date(d.getTime() + 9 * 3600_000).toISOString().slice(0, 19);
  return `${k}+09:00`;
};
const MINUTES = [10, 20, 30];

/** 확정된 상담이 길어질 때 예상 종료를 기록한다(API 37). 상담이 시작된 뒤에만 눌린다. 뒤 상담이 겹치면 서버가 대체 시간을 안내한다 */
export function ConsultDelay({ requestId }: { requestId: string }) {
  const q = useRequest(requestId);
  const delay = useConsultDelay(requestId);
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [min, setMin] = useState(MINUTES[0]);
  const [saved, setSaved] = useState<string | null>(null);
  const booking = q.data?.consultation?.booking;
  if (!booking) return null;
  const start = new Date(booking.period.start);
  const end = new Date(booking.period.end);
  const now = new Date();
  const started = now >= start;
  const base = new Date(Math.max(now.getTime(), saved ? new Date(saved).getTime() : end.getTime()));
  const next = new Date(Math.ceil((base.getTime() + min * 60_000) / 60_000) * 60_000);
  const day = (d: Date) => d.toLocaleDateString("sv-SE", { timeZone: "Asia/Seoul" });
  const tooLate = next.getTime() > end.getTime() + 3 * 3600_000 || day(next) !== day(start);

  const send = () =>
    delay.mutate({ bookingId: booking.id, expectedEndAt: kst(next) }, {
      onSuccess: (r) => {
        setSaved(r.booking.expected_end_at ?? kst(next));
        setOpen(false);
        toast({ kind: "ok", title: "예상 종료를 기록했어요", sub: r.affected_bookings ? `뒤에 이어지는 상담 ${r.affected_bookings}건과 겹쳐요` : undefined });
      },
      onError: (e) => {
        setOpen(false);
        const s = e instanceof ApiError ? e.status : 0;
        toast({ kind: "error", title: s === 403 ? "예약을 맡은 담임만 기록할 수 있어요" : s === 409 ? "확정된 상담만 기록할 수 있어요" : s === 422 ? "이 시간으로는 기록할 수 없어요" : "기록하지 못했어요", sub: s === 422 ? "상담 시간과 날짜를 확인해 주세요" : "연결을 확인하고 다시 눌러 주세요" });
      },
    });

  return (
    <section className="grid gap-2 rounded-2xl bg-card px-4 py-3.5 shadow-card" aria-label="확정된 상담">
      <b className="text-callout">확정된 상담</b>
      <p className="text-[14.5px]">
        {start.toLocaleDateString("ko-KR", { month: "long", day: "numeric", weekday: "short" })} {hm(start)}~{hm(end)} · {booking.room}
        {saved && <span className="ml-1.5 font-semibold text-accent-ink">예상 종료 {hm(new Date(saved))}</span>}
      </p>
      <Button variant="tinted" size="sm" onClick={() => setOpen(true)} disabled={!started} lockedReason={started ? undefined : "상담이 시작된 뒤에 기록할 수 있어요"}>
        상담이 길어져요
      </Button>
      <Sheet open={open} onClose={() => setOpen(false)} title="상담이 얼마나 더 걸리나요?">
        <p className="text-sub text-ink2">뒤에 이어지는 상담과 겹치면 대체 시간을 안내해요. 예약 시간은 그대로 둬요.</p>
        <div className="flex gap-2" role="radiogroup" aria-label="추가 시간">
          {MINUTES.map((m) => (
            <button key={m} type="button" role="radio" aria-checked={min === m} onClick={() => setMin(m)} className={`h-11 flex-1 rounded-md text-callout font-semibold ${min === m ? "bg-brand-fill text-on-brand" : "bg-fill text-ink"}`}>
              {m}분
            </button>
          ))}
        </div>
        <p className="rounded-md bg-g p-3 text-callout">예상 종료 <b>{hm(next)}</b></p>
        <Button loading={delay.isPending} disabled={tooLate} lockedReason={tooLate ? "원래 종료보다 3시간 안, 같은 날로만 기록할 수 있어요" : undefined} onClick={send}>기록하기</Button>
        <Button variant="plain" size="sm" onClick={() => setOpen(false)}>취소</Button>
      </Sheet>
    </section>
  );
}
