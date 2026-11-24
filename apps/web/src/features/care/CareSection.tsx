import { useState } from "react";
import { ApiError } from "@/api/client";
import { MISSING_LABEL, useCareDecision, useCareRequests, type CareItem } from "@/api/care";
import { Icon } from "@/components/Icon";
import { QueryState } from "@/components/QueryState";
import { useToast } from "@/components/Toast";

const TYPE = { pickup: { label: "귀가", icon: "handover" }, medication: { label: "투약", icon: "medication" } } as const;
const FOLD = 4;

/**
 * 아이들이 보낸 귀가·투약 요청. 관찰 기록과 같은 자리에서 확인한다.
 * confirm(내용 확인) → complete(실제로 마침) 두 단계이고, 보호자가 새 글을 쓰면 판이 바뀌어 409가 난다 (문서 3.27).
 */
export function CareSection({ classroomId }: { classroomId?: string }) {
  const q = useCareRequests(classroomId);
  const decide = useCareDecision();
  const toast = useToast();
  const [all, setAll] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);

  const open = (q.data ?? []).filter((c) => c.status !== "completed");
  const done = (q.data ?? []).filter((c) => c.status === "completed");
  const shown = all ? open : open.slice(0, FOLD);

  const run = (c: CareItem) => {
    if (!c.next_action) return;
    setBusyId(c.id);
    decide.mutate(
      { id: c.id, decision: c.next_action, version: c.version },
      {
        onSuccess: () => toast({ kind: "ok", title: c.next_action === "confirm" ? "요청을 확인했어요" : "완료로 기록했어요", sub: c.next_action === "confirm" ? "보호자에게 확인했다는 알림이 가요" : "보호자에게 완료 알림이 가요" }),
        onError: (e) => {
          const conflict = e instanceof ApiError && (e.status === 409);
          toast({
            kind: "error",
            title: conflict ? "보호자가 방금 내용을 바꿨어요" : "처리하지 못했어요",
            sub: conflict ? "최신 내용으로 다시 불러왔어요. 확인하고 다시 눌러 주세요" : "연결을 확인하고 다시 눌러 주세요",
            ...(conflict ? {} : { action: { label: "다시 시도", run: () => run(c) } }),
          });
        },
        onSettled: () => setBusyId(null),
      },
    );
  };

  return (
    <section className="mt-5" aria-label="귀가·투약 요청">
      <div className="mb-2 flex items-baseline justify-between px-1">
        <h2 className="text-footnote font-semibold text-ink2">오늘 들어온 귀가·투약 요청</h2>
        <span className="text-caption font-semibold text-ink2">{q.data ? `확인 필요 ${open.length}건` : ""}</span>
      </div>
      <QueryState queries={[q]} skeleton={2} errorTitle="귀가·투약 요청을 불러오지 못했어요">
        {open.length === 0 ? (
          <p className="rounded-lg bg-card p-4 text-center text-callout text-ink2 shadow-card">{done.length ? `요청 ${done.length}건을 모두 처리했어요` : "들어온 요청이 없어요"}</p>
        ) : (
          <ul className="overflow-hidden rounded-lg bg-card shadow-card">
            {shown.map((c) => {
              const t = TYPE[c.type];
              const missing = c.missing_fields.map((f) => MISSING_LABEL[f] ?? f);
              return (
                <li key={c.id} className="grid gap-2 px-3 py-3 [&+&]:border-t [&+&]:border-sep">
                  <div className="flex items-start gap-3">
                    <span className="grid size-9 shrink-0 place-items-center rounded-md bg-tint text-accent-ink"><Icon name={t.icon} className="size-5" /></span>
                    <span className="min-w-0 flex-1">
                      <span className="flex items-center gap-2">
                        <b className="text-caption font-bold text-accent-ink">{t.label}</b>
                        <span className="text-caption font-semibold text-ink2">{c.status_label}</span>
                      </span>
                      <span className="mt-0.5 block text-callout font-semibold">{c.title}</span>
                      {c.type === "pickup" && c.unregistered_pickup && <span className="mt-1 block text-footnote font-semibold text-danger">등록되지 않은 인계자예요. 누가 데려가는지 꼭 확인해 주세요</span>}
                      {c.type === "medication" && missing.length > 0 && <span className="mt-1 block text-footnote font-semibold text-danger">빠진 정보: {missing.join(" · ")}. 보호자에게 확인해 주세요</span>}
                    </span>
                  </div>
                  {c.next_action && (
                    <button type="button" disabled={busyId === c.id} onClick={() => run(c)} className="h-10 rounded-md bg-tint text-footnote font-semibold text-accent-ink active:scale-[.97] disabled:opacity-50">
                      {c.next_action === "confirm" ? "확인했어요" : c.type === "medication" ? "먹였어요 (완료)" : "인계했어요 (완료)"}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {open.length > FOLD && (
          <button type="button" onClick={() => setAll((v) => !v)} className="mt-2 h-10 w-full rounded-md bg-fill text-footnote font-semibold">
            {all ? "접기" : `${open.length - FOLD}건 더 보기`}
          </button>
        )}
      </QueryState>
    </section>
  );
}
