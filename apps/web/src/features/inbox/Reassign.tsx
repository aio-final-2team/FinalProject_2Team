import { useMemo, useState } from "react";
import { ApiError } from "@/api/client";
import { useAllCards, useReassign } from "@/api/cards";
import { useSession } from "@/app/session";
import { Button } from "@/components/Button";
import { Sheet } from "@/components/Sheet";
import { useToast } from "@/components/Toast";
import type { Card } from "@/domain/types";

/**
 * 원장의 카드 재배정(API 19). 서버에 교사 목록 API가 없어서, 카드 목록에 담당으로 나온 선생님 중에서 고른다.
 * 아직 맡은 카드가 없는 선생님은 목록에 나오지 않는다(교사 목록 API가 생기면 그 목록으로 바꾼다).
 */
export function Reassign({ c }: { c: Card }) {
  const { user } = useSession();
  const all = useAllCards();
  const reassign = useReassign(c.id);
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [pick, setPick] = useState<string>();
  const [reason, setReason] = useState("");

  const current = all.find((x) => x.id === c.id)?.assignee;
  const teachers = useMemo(() => {
    const m = new Map<string, string>();
    for (const x of all) if (x.assignee && x.assignee.id !== user?.id && x.assignee.id !== current?.id) m.set(x.assignee.id, x.assignee.name);
    return [...m].map(([id, name]) => ({ id, name }));
  }, [all, user?.id, current?.id]);

  const locked = c.kind === "director_report" ? "원장 보고 카드는 바꿀 수 없어요" : c.status === "completed" || c.status === "rejected" ? "끝난 카드는 바꿀 수 없어요" : undefined;

  const send = () =>
    reassign.mutate({ assigneeId: pick!, reason: reason.trim() }, {
      onSuccess: () => {
        setOpen(false);
        setPick(undefined);
        setReason("");
        toast({ kind: "ok", title: "담당을 바꿨어요", sub: `${teachers.find((t) => t.id === pick)?.name ?? "새 선생님"}께 알림이 가요` });
      },
      onError: (e) => {
        setOpen(false);
        const s = e instanceof ApiError ? e.status : 0;
        toast({ kind: "error", title: s === 403 ? "원장님만 담당을 바꿀 수 있어요" : s === 409 ? "이미 끝났거나 바꿀 수 없는 카드예요" : s === 404 ? "선생님을 찾지 못했어요" : "담당을 바꾸지 못했어요", sub: s ? undefined : "연결을 확인하고 다시 눌러 주세요" });
      },
    });

  return (
    <>
      <Button variant="tinted" lockedReason={locked} onClick={() => setOpen(true)}>담당 바꾸기</Button>
      <Sheet open={open} onClose={() => setOpen(false)} title="담당 선생님 바꾸기">
        {current && <p className="text-sub text-ink2">지금 담당은 {current.name}이에요.</p>}
        {teachers.length === 0 ? (
          <p className="rounded-md bg-g p-3 text-callout text-ink2">고를 수 있는 선생님이 아직 없어요. 카드를 맡고 있는 다른 선생님이 있을 때 여기에 나와요.</p>
        ) : (
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="새 담당 선생님">
            {teachers.map((t) => (
              <button key={t.id} type="button" role="radio" aria-checked={pick === t.id} onClick={() => setPick(t.id)} className={`h-11 rounded-full px-4 text-callout font-semibold ${pick === t.id ? "bg-brand-fill text-on-brand" : "bg-card text-ink shadow-card"}`}>{t.name}</button>
            ))}
          </div>
        )}
        <label className="grid gap-1.5">
          <span className="text-footnote font-semibold">바꾸는 이유</span>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={500} rows={3} placeholder="예: 상담 일정이 겹쳐서 다른 선생님께 맡겨요" className="rounded-md border-[1.5px] border-line bg-card p-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
        </label>
        <Button loading={reassign.isPending} lockedReason={!pick ? "새 담당 선생님을 골라 주세요" : !reason.trim() ? "바꾸는 이유를 적어 주세요" : undefined} onClick={send}>담당 바꾸기</Button>
        <Button variant="plain" size="sm" onClick={() => setOpen(false)}>닫기</Button>
      </Sheet>
    </>
  );
}
