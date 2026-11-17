import { useEffect, useRef, useState, type ReactNode } from "react";
import { newKey, useCard, useCardAction } from "@/api/cards";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { Sheet } from "@/components/Sheet";
import { SkeletonRows, StateView } from "@/components/StateView";
import { Pill, StatusPill, TypeTag } from "@/components/Tags";
import { useToast } from "@/components/Toast";
import { TYPE_LABEL } from "@/domain/status";
import type { Card, CardAction, Role } from "@/domain/types";
import { BackLink } from "./InboxPage";

type SheetKind = null | "send" | "reject" | "hold" | "complete" | "confirm_slot" | "note" | "reassign";

const Section = ({ title, children }: { title: string; children: ReactNode }) => (
  <section className="grid gap-2">
    <h3 className="px-1 text-sub font-medium text-ink2">{title}</h3>
    {children}
  </section>
);

function ReasonChips({ options, value, onChange }: { options: string[]; value: string; onChange: (v: string) => void }) {
  return (
    <div className="flex flex-wrap gap-1.5" role="radiogroup">
      {options.map((o) => (
        <button key={o} role="radio" aria-checked={value === o} onClick={() => onChange(o)} className={`rounded-full px-3 py-1.5 text-[13px] font-medium transition active:scale-95 ${value === o ? "bg-ink text-card" : "bg-g text-ink hover:bg-fill2"}`}>
          {o}
        </button>
      ))}
    </div>
  );
}

/**
 * T-02 · D-02 카드 상세. 학부모 원문(흰 칸) · 근거(문서 칩) · AI 초안(파란 칸)을 모양으로 나눈다.
 * 긴급·판단 필요 카드에는 AI 초안 칸이 없다. 되돌릴 수 없는 행동은 확인 시트를 거친다.
 * 보내기는 5초 동안 되돌릴 수 있고, 실제 요청은 5초 뒤에 보낸다.
 */
export function CardDetail({ id, role, backTo }: { id: string; role: Exclude<Role, "parent">; backTo: string }) {
  const { data: c, isLoading, isError, refetch } = useCard(id);
  const act = useCardAction(id, role);
  const toast = useToast();
  const [sheet, setSheet] = useState<SheetKind>(null);
  const [reason, setReason] = useState("");
  const [text, setText] = useState("");
  const [draft, setDraft] = useState("");
  const [slot, setSlot] = useState("");
  const [pendingSend, setPendingSend] = useState(false);
  const key = useRef(newKey());
  const sendTimer = useRef<number>(0);

  useEffect(() => {
    if (c) {
      setDraft(c.draft ?? "");
      setSlot(c.slots?.find((s) => s.picked)?.id ?? "");
    }
  }, [c?.id]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => window.clearTimeout(sendTimer.current), []);

  if (isLoading) return <SkeletonRows n={4} />;
  if (isError || !c) return <StateView kind="error" audience="staff" title="카드를 불러오지 못했어요" action={{ label: "다시 시도", run: () => refetch() }} />;

  const open = (k: SheetKind) => {
    key.current = newKey();
    setReason("");
    setText("");
    setSheet(k);
  };
  const run = (body: CardAction, ok: { title: string; sub?: string }) =>
    act.mutate(
      { body, key: key.current },
      {
        onSuccess: () => {
          setSheet(null);
          toast({ kind: "ok", ...ok });
        },
        onError: () => toast({ kind: "error", title: "처리하지 못했어요", sub: "연결을 확인하고 다시 눌러 주세요", action: { label: "다시 시도", run: () => run(body, ok) } }),
      },
    );
  const send = () => {
    setSheet(null);
    setPendingSend(true);
    const body: CardAction = { action: "approve_send", draft };
    const k = key.current;
    sendTimer.current = window.setTimeout(() => {
      act.mutate({ body, key: k }, { onSettled: () => setPendingSend(false) });
    }, 5000);
    toast({
      kind: "undo",
      title: "보냈어요",
      sub: `${c.guardianName}에게`,
      action: {
        label: "되돌리기",
        run: () => {
          window.clearTimeout(sendTimer.current);
          setPendingSend(false);
          toast({ kind: "ok", title: "되돌렸어요", sub: "보내기를 취소했어요" });
        },
      },
    });
  };

  const isOpen = !["completed", "rejected", "sent_or_booked"].includes(c.status) || (c.parentConfirmedAt && c.status === "sent_or_booked");
  const director = role === "director";

  return (
    <article className="mx-auto grid max-w-[720px] gap-5 px-4 pb-40 pt-[max(16px,env(safe-area-inset-top))] lg:px-8 lg:pt-8">
      <BackLink to={backTo} />
      <header className="grid gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <TypeTag type={c.type} />
          <StatusPill status={c.status} role="staff" />
          {c.risk === "urgent" && <Pill tone="urgent">긴급 · {c.urgentReason}</Pill>}
          {c.risk === "judge" && <Pill tone="action">판단 필요</Pill>}
          {c.repeatCount && c.repeatCount >= 3 && <Pill tone="action">반복 {c.repeatCount}번째 · 30일</Pill>}
          {c.escalated && c.status !== "escalated" && <Pill>원장 보고</Pill>}
          {c.check?.passed && <Pill tone="done">검사 통과</Pill>}
        </div>
        <h2 className="text-[22px] font-bold tracking-[-0.02em]">
          {TYPE_LABEL[c.type]} · {c.title}
        </h2>
        <p className="text-sub text-ink2">
          {c.className} · {c.guardianName} · 요청 {c.requestId}
        </p>
      </header>

      {c.risk === "urgent" && (
        <div className="flex gap-2.5 rounded-2xl bg-ink px-4 py-3 text-card">
          <Icon name="urgent" className="mt-0.5 size-5" />
          <p className="text-[14px]">
            <b>긴급 · {c.urgentReason}</b>
            <br />
            AI 초안 없이 바로 올라온 카드예요. 원장님께도 함께 알렸어요.
          </p>
        </div>
      )}
      {c.risk === "judge" && (
        <div className="flex gap-2.5 rounded-2xl bg-tint px-4 py-3 text-accent-ink">
          <Icon name="urgent" className="mt-0.5 size-5" />
          <p className="text-[14px]">
            <b>AI 판단 불확실</b>
            <br />
            교직원 비난인지 확신이 낮아요. 일반이나 긴급으로 다시 분류해 주세요.
          </p>
        </div>
      )}

      <Section title="학부모 원문">
        <blockquote className="rounded-2xl bg-card px-4 py-3.5 text-[15px] leading-relaxed">{c.original}</blockquote>
        {c.summary && <p className="px-1 text-sub text-ink2">AI 요약: {c.summary}</p>}
      </Section>

      {c.sources.length > 0 && (
        <Section title="근거">
          <div className="flex flex-wrap gap-1.5">
            {c.sources.map((s) => (
              <span key={s.doc} className={`inline-flex items-center gap-1.5 rounded-[10px] bg-card px-2.5 py-1.5 text-[12.5px] font-medium ${s.old ? "text-ink3 line-through" : ""}`}>
                <Icon name="document" className="size-3.5 text-accent" />
                {s.doc} · {s.where} · {s.effective.slice(5).replace("-", "/")} 적용
              </span>
            ))}
          </div>
          {c.check?.note && <p className="px-1 text-sub text-ink2">{c.check.note}</p>}
        </Section>
      )}

      {c.slots && (
        <Section title="학부모가 고른 시간 · 하나를 확정해 주세요">
          <div className="overflow-hidden rounded-2xl bg-card" role="radiogroup">
            {c.slots
              .filter((s) => s.picked)
              .map((s) => (
                <label key={s.id} className="flex cursor-pointer items-center gap-3 border-b border-sep px-4 py-3 last:border-0">
                  <input type="radio" name="slot" className="size-5 accent-[var(--accent)]" checked={slot === s.id} onChange={() => setSlot(s.id)} disabled={!!director || !isOpen} />
                  <b className="text-[14.5px]">{s.at}</b>
                  <span className="text-sub text-ink2">{s.mode}</span>
                </label>
              ))}
          </div>
        </Section>
      )}

      {c.risk === "normal" && c.draft !== undefined && (
        <Section title={c.status === "awaiting_review" || c.status === "escalated" ? "AI 초안 · 고칠 수 있어요" : "보낸 답"}>
          <div className="grid gap-1.5 rounded-2xl bg-tint px-4 py-3">
            <span className="inline-flex items-center gap-1 text-cap font-bold text-accent-ink">
              <Icon name="ai" className="size-3.5" />
              AI 초안
            </span>
            {isOpen && !director && c.status !== "sent_or_booked" ? (
              <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={4} className="w-full resize-y bg-transparent text-[15px] leading-relaxed outline-none" aria-label="AI 초안 고치기" />
            ) : (
              <p className="text-[15px] leading-relaxed">{c.draft}</p>
            )}
          </div>
        </Section>
      )}
      {c.risk === "urgent" && isOpen && !director && (
        <Section title="직접 답 쓰기">
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={4} placeholder="확인한 내용을 직접 써 주세요" className="rounded-2xl border-[1.5px] border-transparent bg-card px-4 py-3 text-[15px] outline-none focus:border-accent focus:shadow-[0_0_0_4px_var(--tint)]" />
        </Section>
      )}

      {c.directorNote && (
        <Section title="원장님 지시">
          <p className="rounded-2xl bg-lav-tint px-4 py-3 text-[14.5px] text-ink">{c.directorNote}</p>
        </Section>
      )}

      {c.history.length > 0 && (
        <Section title="처리 이력">
          <ol className="grid gap-1.5 px-1 text-sub text-ink2">
            {c.history.map((h, i) => (
              <li key={i}>
                <b className="text-ink">{h.who}</b> · {h.what} · {new Date(h.at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })}
              </li>
            ))}
          </ol>
        </Section>
      )}

      {/* 아래 고정 행동 칸 */}
      {isOpen && (
        <div className={`glass fixed inset-x-0 z-20 ${director ? "bottom-0 pb-[max(12px,env(safe-area-inset-bottom))]" : "bottom-[calc(64px+env(safe-area-inset-bottom))]"} bg-bar px-4 py-3 shadow-[0_-1px_0_var(--sep)] backdrop-blur-xl backdrop-saturate-[1.8] lg:sticky lg:bottom-4 lg:mx-0 lg:rounded-2xl lg:shadow-[0_8px_30px_rgba(11,31,58,.12),0_0_0_.5px_var(--sep)]`}>
          <div className="mx-auto grid max-w-[720px] gap-2">{director ? <DirectorActions c={c} open={open} /> : <TeacherActions c={c} open={open} draft={draft} slot={slot} pending={pendingSend || act.isPending} run={run} />}</div>
        </div>
      )}

      {/* 확인 시트들 */}
      <Sheet open={sheet === "send"} onClose={() => setSheet(null)} title={c.groupedCount ? `${c.groupedCount}명에게 보낼까요?` : "이 답을 보낼까요?"}>
        <div className="overflow-hidden rounded-xl bg-g text-[14px]">
          <div className="flex justify-between border-b border-sep px-3.5 py-2.5"><span className="text-ink2">받는 사람</span><b>{c.guardianName}</b></div>
          {c.sources[0] && <div className="flex justify-between px-3.5 py-2.5"><span className="text-ink2">근거</span><b>{c.sources[0].doc} {c.sources[0].where}</b></div>}
        </div>
        <p className="rounded-xl bg-g px-3.5 py-3 text-[14px] leading-relaxed">{draft}</p>
        <p className="text-sub text-ink2">보낸 뒤 5초 안에는 되돌릴 수 있어요.</p>
        <Button onClick={send} lockedReason={draft.trim().length < 2 ? "보낼 답을 써 주세요" : undefined}>보내기</Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>취소</Button>
      </Sheet>

      <Sheet open={sheet === "reject"} onClose={() => setSheet(null)} title="이 요청을 반려할까요?">
        <p className="text-sub text-ink2">고른 이유가 학부모에게 함께 전달돼요.</p>
        <ReasonChips options={["개인정보 요청", "원 운영 범위 밖", "중복 요청"]} value={reason} onChange={setReason} />
        <Button variant="danger" loading={act.isPending} lockedReason={reason ? undefined : "이유를 고르면 반려할 수 있어요"} onClick={() => run({ action: "reject", reason }, { title: "반려했어요", sub: reason })}>반려하기</Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>취소</Button>
      </Sheet>

      <Sheet open={sheet === "hold"} onClose={() => setSheet(null)} title="언제까지 보류할까요?">
        <p className="text-sub text-ink2">학부모에게는 예정일만 보이고, 이유는 교직원끼리만 봐요.</p>
        <ReasonChips options={["원장님 확인 필요", "자료 확인 중", "학부모 통화 예정"]} value={reason} onChange={setReason} />
        <ReasonChips options={["내일", "모레", "11/20(목)"]} value={text} onChange={setText} />
        <Button loading={act.isPending} lockedReason={reason && text ? undefined : "이유와 예정일을 골라 주세요"} onClick={() => run({ action: "hold", reason, until: text }, { title: "보류했어요", sub: `${text}까지` })}>보류하기</Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>취소</Button>
      </Sheet>

      <Sheet open={sheet === "complete"} onClose={() => setSheet(null)} title="이 민원을 완료할까요?">
        <p className="text-sub text-ink2">학부모가 {c.parentConfirmedAt ? "확인했어요" : "아직 확인하지 않았어요"}. 완료하면 학부모 화면에 '완료'로 보여요.</p>
        <Button loading={act.isPending} onClick={() => run({ action: "complete" }, { title: "처리 완료했어요", sub: "완료 필터로 옮겼어요" })}>처리 완료</Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>취소</Button>
      </Sheet>

      <Sheet open={sheet === "confirm_slot"} onClose={() => setSheet(null)} title="이 시간으로 확정할까요?">
        <p className="rounded-xl bg-g px-3.5 py-3 text-[15px] font-semibold">{c.slots?.find((s) => s.id === slot)?.at} · {c.slots?.find((s) => s.id === slot)?.mode}</p>
        <p className="text-sub text-ink2">확정하면 예약이 저장되고 학부모에게 알림이 가요. 저장 직전에 다른 예약과 겹치는지 다시 확인해요.</p>
        <Button loading={act.isPending} onClick={() => run({ action: "confirm_slot", slotId: slot }, { title: "상담을 확정했어요", sub: c.slots?.find((s) => s.id === slot)?.at })}>확정하기</Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>취소</Button>
      </Sheet>

      <Sheet open={sheet === "note"} onClose={() => setSheet(null)} title="담임에게 지시 남기기">
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} placeholder="예: 규정은 유지하되 개별 기상 시간 조정은 허용해 주세요." className="rounded-xl bg-g px-3.5 py-3 text-[15px] outline-none focus:shadow-[0_0_0_4px_var(--tint)]" />
        <Button loading={act.isPending} lockedReason={text.trim().length < 2 ? "지시 내용을 써 주세요" : undefined} onClick={() => run({ action: "note", text }, { title: "지시를 남겼어요", sub: "담임 카드에 보여요" })}>남기기</Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>취소</Button>
      </Sheet>

      <Sheet open={sheet === "reassign"} onClose={() => setSheet(null)} title="다른 선생님께 맡길까요?">
        <ReasonChips options={["담임 부재", "대체 담임 기간", "업무 조정"]} value={reason} onChange={setReason} />
        <Button loading={act.isPending} lockedReason={reason ? undefined : "이유를 고르면 맡길 수 있어요"} onClick={() => run({ action: "note", text: `재배정 · ${reason}` }, { title: "재배정했어요", sub: reason })}>재배정</Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>취소</Button>
      </Sheet>
    </article>
  );
}

function TeacherActions({ c, open, draft, slot, pending, run }: { c: Card; open: (k: SheetKind) => void; draft: string; slot: string; pending: boolean; run: (b: CardAction, ok: { title: string; sub?: string }) => void }) {
  if (c.risk === "judge")
    return (
      <>
        <p className="text-center text-sub text-ink2">일반이나 긴급으로 다시 분류해 주세요</p>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="tinted" loading={pending} onClick={() => run({ action: "reclassify", risk: "normal", reason: "담임 판단" }, { title: "일반으로 분류했어요", sub: "확인 필요로 옮겼어요" })}>일반으로</Button>
          <Button variant="navy" loading={pending} onClick={() => run({ action: "reclassify", risk: "urgent", reason: "담임 판단" }, { title: "긴급으로 분류했어요", sub: "원장님께도 알렸어요" })}>긴급으로</Button>
        </div>
      </>
    );
  if (c.status === "sent_or_booked" && c.parentConfirmedAt)
    return <Button icon="approve" onClick={() => open("complete")}>처리 완료</Button>;
  if (c.type === "consult")
    return (
      <div className="grid grid-cols-[1fr_2fr] gap-2">
        <Button variant="gray" onClick={() => open("reject")}>거절</Button>
        <Button onClick={() => open("confirm_slot")} lockedReason={slot ? undefined : "확정할 시간을 골라 주세요"}>확정하기</Button>
      </div>
    );
  return (
    <>
      <div className="grid grid-cols-3 gap-2">
        <Button variant="gray" size="sm" onClick={() => open("hold")}>보류</Button>
        <Button variant="gray" size="sm" onClick={() => open("reject")}>반려</Button>
        <Button variant="gray" size="sm" disabled={c.escalated} onClick={() => run({ action: "escalate" }, { title: "원장님께 올렸어요" })}>{c.escalated ? "원장 보고됨" : "원장님께"}</Button>
      </div>
      <Button loading={pending} onClick={() => open("send")} lockedReason={draft.trim().length < 2 ? "보낼 답을 써 주세요" : undefined}>
        {c.groupedCount ? `승인하고 ${c.groupedCount}명에게 보내기` : "승인하고 보내기"}
      </Button>
    </>
  );
}

function DirectorActions({ c, open }: { c: Card; open: (k: SheetKind) => void }) {
  return (
    <>
      <p className="text-center text-sub text-ink2">민원 회신은 담임 승인으로만 나가요</p>
      <div className="grid grid-cols-2 gap-2">
        <Button variant="tinted" onClick={() => open("reassign")}>재배정</Button>
        <Button onClick={() => open("note")}>{c.directorNote ? "지시 고치기" : "지시 남기기"}</Button>
      </div>
    </>
  );
}
