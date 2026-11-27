import { useState } from "react";
import { ApiError } from "@/api/client";
import { MISSING_LABEL, useCareDecision, useCareRequests, type CareItem } from "@/api/care";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { QueryState } from "@/components/QueryState";
import { Sheet } from "@/components/Sheet";
import { useToast } from "@/components/Toast";
import { term } from "@/domain/wording";

const TYPE = { pickup: { label: "귀가", icon: "handover" }, medication: { label: "투약", icon: "medication" } } as const;
const FOLD = 4;

/**
 * 아이들이 보낸 귀가·투약 요청. 확인 → 완료 두 단계이고, 할 수 없는 요청은 사유를 적어 거절한다(보호자에게 전달).
 * 보호자가 새 글을 쓰거나 입력을 고치면 판이 바뀌어 409가 난다 (문서 3.27). 학부모가 취소한 요청은 status_label이 '취소함'으로 온다.
 */
export function CareSection({ classroomId, all }: { classroomId?: string; all?: boolean }) {
  const q = useCareRequests(classroomId, all);
  const decide = useCareDecision();
  const toast = useToast();
  const [more, setMore] = useState(false);
  const [done, setDone] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<CareItem | null>(null);
  const [reason, setReason] = useState("");

  const [tab, setTab] = useState<"all" | "pickup" | "medication">("all");
  const isOpen = (c: CareItem) => c.status === "received" || c.status === "assigned";
  const everything = q.data ?? [];
  const list = tab === "all" ? everything : everything.filter((c) => c.type === tab);
  const open = list.filter(isOpen);
  const closed = list.filter((c) => c.status === "completed" || c.status === "rejected");
  const shown = more ? open : open.slice(0, FOLD);
  const count = (t: "pickup" | "medication") => everything.filter((c) => c.type === t && isOpen(c)).length;
  const TABS = [
    { k: "all", label: "전체", n: everything.filter(isOpen).length },
    { k: "pickup", label: "귀가", n: count("pickup") },
    { k: "medication", label: "투약", n: count("medication") },
  ] as const;

  const fail = (e: unknown, c: CareItem, what: string, retry: () => void) => {
    const conflict = e instanceof ApiError && e.status === 409;
    toast({
      kind: "error",
      title: conflict ? "보호자가 방금 내용을 바꿨어요" : `${what} 기록을 남기지 못했어요`,
      sub: conflict ? "최신 내용으로 다시 불러왔어요.\n확인하고 다시 눌러 주세요" : "연결을 확인하고 다시 눌러 주세요",
      ...(conflict ? {} : { action: { label: "다시 시도", run: retry } }),
    });
    void c;
  };

  const run = (c: CareItem) => {
    if (!c.next_action) return;
    const what = c.next_action === "confirm" ? "확인" : "완료";
    setBusyId(c.id);
    decide.mutate(
      { id: c.id, decision: c.next_action, version: c.version, type: c.type },
      {
        onSuccess: () => toast({ kind: "ok", title: c.next_action === "confirm" ? "요청을 확인했어요" : "완료로 기록했어요", sub: c.next_action === "confirm" ? "보호자에게 확인했다는 알림이 가요" : "보호자에게 완료 알림이 가요" }),
        onError: (e) => fail(e, c, what, () => run(c)),
        onSettled: () => setBusyId(null),
      },
    );
  };

  const reject = () => {
    if (!rejecting) return;
    const c = rejecting;
    decide.mutate(
      { id: c.id, decision: "reject", version: c.version, reason_text: reason.trim() },
      {
        onSuccess: () => { setRejecting(null); setReason(""); toast({ kind: "ok", title: "요청을 거절했어요", sub: "적은 사유가 보호자에게 전달돼요" }); },
        onError: (e) => { setRejecting(null); fail(e, c, "거절", () => setRejecting(c)); },
      },
    );
  };

  return (
    <section className="mt-5" aria-label="귀가·투약 요청">
      <div className="mb-2 flex items-baseline justify-between px-1">
        <h2 className="text-footnote font-semibold text-ink2">오늘 들어온 귀가·투약 요청</h2>
        <span className="text-caption font-semibold text-ink2">{q.data ? `확인 필요 ${open.length}건` : ""}</span>
      </div>
      <div className="mb-3 flex gap-2" role="tablist" aria-label="요청 종류">
        {TABS.map((t) => (
          <button key={t.k} type="button" role="tab" aria-selected={tab === t.k} onClick={() => { setTab(t.k); setMore(false); }} className={`h-9 rounded-full px-3.5 text-footnote font-semibold ${tab === t.k ? "bg-ink text-card" : "bg-card text-ink shadow-card"}`}>
            {t.label} <span className="tabular-nums">{t.n}</span>
          </button>
        ))}
      </div>
      <QueryState queries={[q]} skeleton={2} errorTitle="귀가·투약 요청을 불러오지 못했어요">
        {open.length === 0 ? (
          <p className="rounded-lg bg-card p-4 text-center text-callout text-ink2 shadow-card">{closed.length ? `요청 ${closed.length}건을 모두 처리했어요` : tab === "all" ? "들어온 요청이 없어요" : `들어온 ${TYPE[tab].label} 요청이 없어요`}</p>
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
                        {c.child_name && <b className="text-callout">{c.child_name}</b>}
                        <b className="text-caption font-bold text-accent-ink">{t.label}</b>
                        <span className="text-caption font-semibold text-ink2">{term(c.status_label)}</span>
                      </span>
                      <span className="mt-0.5 block text-callout font-semibold">{c.title}</span>
                      {c.type === "pickup" && c.unregistered_pickup && <span className="mt-1 block text-footnote font-semibold text-danger">등록되지 않은 인계자예요. 누가 데려가는지 꼭 확인해 주세요</span>}
                      {c.type === "medication" && missing.length > 0 && <span className="mt-1 block text-footnote font-semibold text-danger">빠진 정보: {missing.join(" · ")}. 보호자에게 확인해 주세요</span>}
                    </span>
                  </div>
                  {c.next_action && (
                    <div className="grid grid-cols-[1fr_2fr] gap-2">
                      <button type="button" disabled={busyId === c.id} onClick={() => { setReason(""); setRejecting(c); }} className="h-10 rounded-md bg-fill text-footnote font-semibold text-ink active:scale-[.97] disabled:opacity-50">거절</button>
                      <button type="button" disabled={busyId === c.id} onClick={() => run(c)} className="h-10 rounded-md bg-tint text-footnote font-semibold text-accent-ink active:scale-[.97] disabled:opacity-50">
                        {c.next_action === "confirm" ? "확인했어요" : c.type === "medication" ? "먹였어요" : "인계했어요"}
                      </button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        )}
        {open.length > FOLD && (
          <button type="button" onClick={() => setMore((v) => !v)} className="mt-2 h-10 w-full rounded-md bg-fill text-footnote font-semibold">
            {more ? "접기" : `${open.length - FOLD}건 더 보기`}
          </button>
        )}

        {closed.length > 0 && (
          <div className="mt-5">
            <button type="button" aria-expanded={done} onClick={() => setDone((v) => !v)} className="flex w-full items-center justify-between px-1 text-footnote font-semibold text-ink2">
              <span>처리한 요청 {closed.length}건</span>
              <Icon name="chevR" className={`size-4 transition-transform ${done ? "rotate-90" : ""}`} />
            </button>
            {done && (
              <ul className="mt-2 overflow-hidden rounded-lg bg-card shadow-card [&>li+li]:border-t [&>li+li]:border-sep">
                {closed.map((c) => (
                  <li key={c.id} className="flex items-center gap-3 px-3 py-2.5">
                    <span className="grid size-8 shrink-0 place-items-center rounded-md bg-fill"><Icon name={TYPE[c.type].icon} className="size-4" /></span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-callout font-semibold">{c.child_name ? `${c.child_name} · ` : ""}{c.title}</span>
                      <span className="text-caption text-ink2">{TYPE[c.type].label}</span>
                    </span>
                    <span className={`shrink-0 text-caption font-semibold ${c.status === "completed" ? "text-ok" : "text-ink2"}`}>{c.status === "completed" ? "완료" : term(c.status_label)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </QueryState>

      <Sheet open={!!rejecting} onClose={() => setRejecting(null)} title="이 요청을 거절할까요?">
        <p className="text-footnote text-ink2">{rejecting?.child_name ? `${rejecting.child_name}의 ` : ""}{rejecting ? TYPE[rejecting.type].label : ""} 요청이에요. 적은 사유가 보호자에게 전달돼요.</p>
        <label className="grid gap-1.5">
          <span className="text-footnote font-semibold">사유</span>
          <textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={1000} rows={4} placeholder="예: 투약 의뢰서가 없어서 약을 먹일 수 없어요" className="rounded-md border-[1.5px] border-line bg-card px-3 py-2.5 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
        </label>
        <Button variant="danger" loading={decide.isPending} lockedReason={reason.trim() ? undefined : "사유를 적어 주세요"} onClick={reject}>거절하기</Button>
        <Button variant="plain" size="sm" onClick={() => setRejecting(null)}>취소</Button>
      </Sheet>
    </section>
  );
}
