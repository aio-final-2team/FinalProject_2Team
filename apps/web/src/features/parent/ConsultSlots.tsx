import { useState } from "react";
import { ApiError } from "@/api/client";
import { slotLabel, useChooseSlots, type RequestDetail } from "@/api/requests";
import { PrimaryButton, SubButton } from "@/components/Dock";
import { useToast } from "@/components/Toast";

/**
 * 상담 시간 고르기 (API 8). 후보에서 가능한 시간을 1~3개 고르면 담임이 그중 하나로 확정한다.
 * 맞는 시간이 없으면 원하는 시간을 적어 후보를 다시 받는다. 확정되면 예약 시간을 보여 준다.
 */
export function ConsultSlots({ requestId, status, consultation }: { requestId: string; status: string; consultation: NonNullable<RequestDetail["consultation"]> }) {
  const choose = useChooseSlots(requestId);
  const toast = useToast();
  const [picked, setPicked] = useState<number[]>([]);
  const [noFit, setNoFit] = useState(false);
  const [wish, setWish] = useState("");
  const live = consultation.slots.filter((s) => s.status !== "discarded");
  const booked = consultation.booking;
  const canPick = !booked && (status === "needs_info" || status === "awaiting_review") && live.some((s) => s.status === "proposed" || s.status === "chosen_by_parent");

  const fail = (e: unknown) => {
    const code = e instanceof ApiError ? e.code : undefined;
    toast({
      kind: "error",
      title: code === "SLOT_TAKEN" ? "그 시간은 이미 찼어요" : code === "SLOT_PAST" ? "이미 시작한 시간이에요" : "시간을 보내지 못했어요",
      sub: code === "SLOT_TAKEN" || code === "SLOT_PAST" ? "새 후보를 불러왔어요.\n다시 골라 주세요" : "연결을 확인하고 다시 눌러 주세요",
    });
    setPicked([]);
  };
  const submit = () =>
    choose.mutate(noFit ? { none_fit: true, preferred_times: wish.trim() } : { slot_ids: picked }, {
      onSuccess: () => { toast({ kind: "ok", title: noFit ? "원하는 시간을 알렸어요" : "시간을 보냈어요", sub: noFit ? "새 후보를 불러왔어요. 다시 골라 주세요" : "선생님이 확인하고 확정해요" }); setPicked([]); setNoFit(false); setWish(""); },
      onError: fail,
    });

  if (booked) {
    return (
      <section className="mt-3 rounded-lg bg-tint p-3" aria-label="상담 예약">
        <b className="block text-callout text-accent-ink">상담 예약이 확정됐어요</b>
        <p className="mt-1 text-headline font-bold">{slotLabel(booked.period)}</p>
        <p className="text-footnote text-ink2">{booked.room}</p>
      </section>
    );
  }
  if (!live.length) return null;

  return (
    <section className="mt-3 rounded-lg bg-card p-3 shadow-card" aria-label="상담 시간">
      <b className="block text-callout">{canPick ? "상담 가능한 시간을 골라 주세요" : "상담 시간 후보"}</b>
      {canPick && <p className="mt-0.5 text-footnote text-ink2">가능한 시간을 1~3개 고르면 선생님이 하나로 확정해요. 확정하기 전에는 예약이 아니에요.</p>}
      <ul className="mt-2 grid gap-2" role="group" aria-label="후보 시간">
        {live.map((s) => {
          const on = picked.includes(s.id) || (s.status === "chosen_by_parent" && picked.length === 0 && !noFit);
          return (
            <li key={s.id}>
              <button
                type="button"
                disabled={!canPick || noFit}
                aria-pressed={on}
                onClick={() => setPicked((p) => (p.includes(s.id) ? p.filter((x) => x !== s.id) : p.length < 3 ? [...p, s.id] : p))}
                className={`flex min-h-12 w-full items-center gap-3 rounded-md border-[1.5px] px-3 py-2 text-left ${on ? "border-accent bg-tint" : "border-sep bg-g"} disabled:opacity-60`}
              >
                <span aria-hidden className={`grid size-5 shrink-0 place-items-center rounded-full border-2 ${on ? "border-accent bg-accent text-on-accent" : "border-line"}`}>{on && <svg viewBox="0 0 24 24" className="size-3" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>}</span>
                <span className="min-w-0 flex-1"><b className="block text-callout">{slotLabel(s.period)}</b><span className="text-caption text-ink2">{s.room}{s.status === "chosen_by_parent" ? " · 내가 고른 시간" : ""}</span></span>
              </button>
            </li>
          );
        })}
      </ul>
      {canPick && (
        <div className="mt-3 grid gap-2">
          {noFit && (
            <label className="grid gap-1.5">
              <span className="text-footnote font-semibold">원하는 시간</span>
              <input value={wish} maxLength={200} onChange={(e) => setWish(e.target.value)} placeholder="예: 다음 주 화요일 오후" className="h-12 rounded-md border-[1.5px] border-line bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
            </label>
          )}
          <PrimaryButton loading={choose.isPending} disabled={noFit ? !wish.trim() : picked.length === 0} onClick={submit}>{noFit ? "원하는 시간 보내기" : `이 시간으로 보내기${picked.length ? ` (${picked.length})` : ""}`}</PrimaryButton>
          {status === "needs_info" && <SubButton tone="gray" className="h-11" onClick={() => { setNoFit((v) => !v); setPicked([]); }}>{noFit ? "후보에서 고를게요" : "맞는 시간이 없어요"}</SubButton>}
        </div>
      )}
    </section>
  );
}
