import { useMemo, useState } from "react";
import { ApiError } from "@/api/client";
import { useAllCards, useReassign } from "@/api/cards";
import { useTeachers } from "@/api/staff";
import { useSession } from "@/app/session";
import { Button } from "@/components/Button";
import { Sheet } from "@/components/Sheet";
import { useToast } from "@/components/Toast";
import type { Card } from "@/domain/types";

/**
 * 원장의 카드 재배정(API 19). 고를 선생님은 선생님 목록 API(API 70)에서 받는다.
 * 아직 맡은 카드가 없는 선생님과 반이 없는 보조 교사도 나온다.
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
  const list = useTeachers(open);
  /* 지금 담당과 나는 빼고, 이름 옆에 지금 맡은 반을 붙인다 */
  const teachers = useMemo(
    () => (list.data ?? []).filter((t) => t.id !== user?.id && t.id !== current?.id).map((t) => ({ id: t.id, name: t.display_name, label: t.classrooms.length ? `${t.display_name} · ${t.classrooms.map((c) => c.name).join(", ")}` : t.display_name })),
    [list.data, user?.id, current?.id],
  );

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
        {list.isLoading ? (
          <p className="rounded-md bg-g p-3 text-callout text-ink2">선생님 목록을 불러오고 있어요</p>
        ) : list.isError ? (
          <p role="alert" className="rounded-md bg-g p-3 text-callout text-ink2">선생님 목록을 불러오지 못했어요. 닫고 다시 열어 주세요.</p>
        ) : teachers.length === 0 ? (
          <p className="rounded-md bg-g p-3 text-callout text-ink2">바꿀 수 있는 다른 선생님이 없어요.</p>
        ) : (
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="새 담당 선생님">
            {teachers.map((t) => (
              <button key={t.id} type="button" role="radio" aria-checked={pick === t.id} onClick={() => setPick(t.id)} className={`h-11 rounded-full px-4 text-callout font-semibold ${pick === t.id ? "bg-brand-fill text-on-brand" : "bg-card text-ink shadow-card"}`}>{t.label}</button>
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
