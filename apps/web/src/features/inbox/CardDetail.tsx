import { useEffect, useRef, useState, type ReactNode } from "react";
import { newKey, useCard, useCardAction } from "@/api/cards";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { Sheet } from "@/components/Sheet";
import { SkeletonRows, StateView } from "@/components/StateView";
import { Pill, StatusPill, TypeTag } from "@/components/Tags";
import { useToast } from "@/components/Toast";
import { REASON_LABEL, useRuleDecision } from "@/api/memory";
import type { Card, CardAction, Role } from "@/domain/types";
import { fmtDateTime } from "@/domain/datetime";
import { BackLink } from "./InboxPage";

/** API 3.7 warnings[] 코드를 교사가 읽는 말로 */
const WARNING: Record<string, string> = {
  stale_evidence: "옛 판 자료가 근거에 섞여 있어요. 최신 자료와 맞는지 확인해 주세요",
  no_evidence: "답변할 근거 자료를 찾지 못했어요. 직접 답을 써 주세요",
  law_unchecked: "법령 근거를 확인하지 못했어요. 법적 내용은 직접 확인해 주세요",
  check_unavailable: "검사 AI가 이 초안을 검사하지 못했어요. 보내기 전에 직접 읽어 주세요",
  notify_failed: "원장님께 가는 알림을 만들지 못했어요. 원장님께 직접 알려 주세요",
};

type SheetKind = null | "send" | "reject" | "reject_time" | "hold" | "complete" | "confirm_slot" | "note" | "reclassify";

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
  const qc = useQueryClient();
  const act = useCardAction(id, role);
  const toast = useToast();
  const [sheet, setSheet] = useState<SheetKind>(null);
  const [reason, setReason] = useState("");
  const [text, setText] = useState("");
  const [draft, setDraft] = useState("");
  const reopened = !!c?.previousText && !c?.draft;
  /* 같은 문장을 제목, 원문, 요약에서 되풀이하지 않는다 */
  const same = (x?: string | null, y?: string | null) => { const n = (t?: string | null) => (t ?? "").replace(/[\s"'“”.…]/g, ""); return !!x && !!y && (n(x).startsWith(n(y)) || n(y).startsWith(n(x))); };
  const showOriginal = !!c?.original && !same(c.original, c.title);
  const showSummary = !!c?.summary && !same(c.summary, c.original) && !same(c.summary, c.title);
  const [slot, setSlot] = useState("");
  const [pendingSend, setPendingSend] = useState(false);
  const key = useRef(newKey());
  const sendTimer = useRef<number>(0);
  const busy = useRef(false); /* 같은 순간 두 번 눌려도 요청은 한 번만 보낸다 */
  const draftKey = `yuchion.cardDraft.${id}`;

  useEffect(() => {
    if (c) {
      /* 고치다 나간 초안이 있으면(서버 초안이 그대로일 때만) 되살린다 */
      let saved = c.draft ?? "";
      try { const v = JSON.parse(localStorage.getItem(draftKey) ?? "null"); if (v && v.base === (c.draft ?? "") && typeof v.text === "string") saved = v.text; } catch { /* 저장이 막혀도 서버 초안으로 시작 */ }
      setDraft(saved);
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
  /** 실패 처리: 판 충돌·이미 처리됨은 최신 상세를 다시 불러오고, 그 밖의 실패는 다시 시도를 준다 */
  const fail = (error: unknown, retry: () => void) => {
    if (error instanceof ApiError && (error.code === "CARD_VERSION_CONFLICT" || error.code === "ALREADY_DECIDED")) {
      setSheet(null);
      qc.invalidateQueries({ queryKey: ["cards"] });
      toast({ kind: "error", title: error.code === "ALREADY_DECIDED" ? "이미 처리된 카드예요" : "카드가 방금 바뀌었어요", sub: "최신 내용으로 다시 불러왔어요.\n확인하고 다시 처리해 주세요" });
      return;
    }
    toast({ kind: "error", title: "처리하지 못했어요", sub: error instanceof ApiError ? "서버에서 처리하지 못했어요.\n잠시 뒤 다시 눌러 주세요" : "연결을 확인하고 다시 눌러 주세요", action: { label: "다시 시도", run: retry } });
  };
  const editDraft = (v: string) => {
    setDraft(v);
    try { if (v === (c.draft ?? "")) localStorage.removeItem(draftKey); else localStorage.setItem(draftKey, JSON.stringify({ base: c.draft ?? "", text: v })); } catch { /* 이번 화면에서만 유지 */ }
  };
  const run = (body: CardAction, ok: { title: string; sub?: string }) => {
    if (busy.current) return;
    busy.current = true;
    act.mutate(
      { body, card: c, key: key.current },
      {
        onSettled: () => { busy.current = false; },
        onSuccess: () => {
          try { localStorage.removeItem(draftKey); } catch { /* 무시 */ }
          setSheet(null);
          toast({ kind: "ok", ...ok });
        },
        onError: (error) => fail(error, () => run(body, ok)),
      },
    );
  };
  const send = () => {
    if (pendingSend) return;
    setSheet(null);
    setPendingSend(true);
    const body: CardAction = { action: "approve_send", draft };
    const k = key.current;
    sendTimer.current = window.setTimeout(() => {
      act.mutate({ body, card: c, key: k }, { onSuccess: () => { try { localStorage.removeItem(draftKey); } catch { /* 무시 */ } }, onError: (e) => fail(e, () => send()), onSettled: () => setPendingSend(false) });
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

  const isOpen = !["completed", "rejected", "sent_or_booked"].includes(c.status) || ((c.parentConfirmedAt || c.type === "complaint") && c.status === "sent_or_booked");
  const director = role === "director";
  /* 원장 보고 카드는 원장만 처리한다(API 결정 403). 교사는 내용만 본다 */
  const reportOnly = !director && c?.kind === "director_report";
  const holdDates = [1, 2, 7].map((days) => {
    const d = new Date();
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
  });

  return (
    <article className="mx-auto grid max-w-[720px] gap-5 px-4 pb-40 pt-[max(8px,env(safe-area-inset-top))] lg:px-8 lg:pt-4">
      <div>
        <div className="flex min-h-[52px] items-center"><BackLink to={backTo} /></div>
      <header className="grid gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <TypeTag type={c.type} />
          <StatusPill status={c.status} role="staff" />
          {c.messages?.some((m) => m.from === "ai") && <Pill tone="wait">바로 안내함</Pill>}
          {c.risk === "urgent" && <Pill tone="urgent">긴급 · {c.urgentReason}</Pill>}
          {c.risk === "judge" && <Pill tone="action">판단 필요</Pill>}
          {c.repeatCount && c.repeatCount >= 3 && <Pill tone="action">반복 {c.repeatCount}번째 · 30일</Pill>}
          {c.escalated && c.status !== "escalated" && <Pill>원장 보고</Pill>}
          {c.check?.passed && <Pill tone="done">검사 통과</Pill>}
          {c.check && !c.check.passed && <Pill tone="action">검사 확인 필요</Pill>}
          {c.noEvidence && !c.warnings?.length && <Pill tone="action">근거 없음</Pill>}
        </div>
        <h1 className="text-large-title font-bold tracking-[-0.025em]">{c.title}</h1>
        {[c.className, c.childName, c.requesterName].filter(Boolean).length > 0 && (
          <p className="text-sub text-ink2">{[c.className, c.childName, c.requesterName].filter(Boolean).join(" · ")}</p>
        )}
      </header>
      </div>

      {reportOnly && (
        <p className="rounded-2xl bg-lav-tint px-4 py-3 text-callout text-ink">원장님께 보고한 카드예요. 원장님이 확인한 뒤 이어서 처리돼요. 보호자에게 보낼 답은 같은 요청의 답장 카드에서 써 주세요.</p>
      )}

      {!reportOnly && c.kind !== "rule_proposal" && (c.warnings?.length || (c.check && !c.check.passed && c.check.issues?.length)) ? (
        <ul className="grid gap-1.5 rounded-2xl bg-card px-4 py-3 text-[14px]" aria-label="확인해 주세요">
          {c.warnings?.map((w) => (
            <li key={w} className="flex gap-2">
              <span className="font-bold text-accent-ink">확인</span>
              <span>{WARNING[w] ?? w}</span>
            </li>
          ))}
          {c.check && !c.check.passed && c.check.issues?.map((i) => (
            <li key={i} className="flex gap-2">
              <span className="font-bold text-accent-ink">검사 AI</span>
              <span>{i}</span>
            </li>
          ))}
        </ul>
      ) : null}

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

      {c.kind === "rule_proposal" && c.rule && (
        <Section title="AI가 제안하는 규칙">
          <div className="rounded-2xl bg-lav-tint px-4 py-3.5">
            <b className="block text-caption font-bold text-lav">{REASON_LABEL[c.rule.reasonCode] ?? c.rule.reasonCode}</b>
            <p className="mt-1 text-[15px] leading-relaxed">{c.rule.text}</p>
          </div>
          <p className="px-1 text-sub text-ink2">같은 이유로 세 번 이상 거절해서 AI가 제안해요. 켜면 AI가 비슷한 카드를 만들 때 참고할 수 있어요.</p>
        </Section>
      )}
      {c.kind === "rule_proposal" ? null : c.messages && c.messages.length > 1 ? (
        <Section title="주고받은 글">
          <ul className="grid gap-2" aria-label="주고받은 글">
            {c.messages.map((m) => (
              <li key={m.id} className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-callout ${m.from === "teacher" ? "ml-auto rounded-br-sm bg-brand-fill text-on-brand" : m.from === "ai" ? "rounded-bl-sm bg-lav-tint" : m.from === "system" ? "rounded-bl-sm bg-fill" : "rounded-bl-sm bg-card shadow-card"}`}>
                <span className="mb-0.5 block text-caption font-semibold opacity-70">{m.from === "parent" ? "학부모" : m.from === "teacher" ? "선생님" : m.from === "ai" ? "바로 안내 · 정해진 문구" : "시스템"}</span>
                <span className="whitespace-pre-line break-keep">{m.body}</span>
              </li>
            ))}
          </ul>
          {showSummary && <p className="px-1 text-sub text-ink2">AI 요약: {c.summary}</p>}
        </Section>
      ) : (
        <>
          {showOriginal && (
            <Section title="학부모 원문">
              <blockquote className="rounded-2xl bg-card px-4 py-3.5 text-[15px] leading-relaxed">{c.original}</blockquote>
            </Section>
          )}
          {showSummary && <p className="px-1 text-sub text-ink2">AI 요약: {c.summary}</p>}
        </>
      )}
      {reopened && (
        <Section title="지난 답">
          <p className="rounded-2xl bg-g px-4 py-3 text-[14.5px] text-ink2">{c.previousText}</p>
          <p className="px-1 text-sub text-ink2">학부모가 글을 더 남겨서 카드가 다시 열렸어요. 새 답을 써 주세요.</p>
        </Section>
      )}

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
        <Section title="학부모가 고른 시간, 하나를 확정해 주세요">
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
        <Section title={c.status === "awaiting_review" || c.status === "escalated" ? "AI 초안, 고칠 수 있어요" : "보낸 답"}>
          <div className="grid gap-1.5 rounded-2xl bg-tint px-4 py-3">
            <span className="inline-flex items-center gap-1 text-cap font-bold text-accent-ink">
              <Icon name="ai" className="size-3.5" />
              AI 초안
            </span>
            {isOpen && !director && c.status !== "sent_or_booked" ? (
              <textarea value={draft} onChange={(e) => editDraft(e.target.value)} rows={4} className="w-full resize-y bg-transparent text-[15px] leading-relaxed outline-none" aria-label="AI 초안 고치기" />
            ) : (
              <p className="text-[15px] leading-relaxed">{c.draft}</p>
            )}
          </div>
        </Section>
      )}
      {(c.risk === "urgent" || (c.noEvidence && !c.draft) || reopened) && isOpen && !director && (
        <Section title={reopened ? "새 답 쓰기" : "직접 답 쓰기"}>
          <textarea value={draft} onChange={(e) => editDraft(e.target.value)} rows={4} placeholder={reopened ? "보호자의 새 글에 대한 답을 써 주세요" : c.noEvidence ? "자료에서 근거를 찾지 못했어요. 확인한 내용을 직접 써 주세요" : "확인한 내용을 직접 써 주세요"} className="rounded-2xl border-[1.5px] border-transparent bg-card px-4 py-3 text-[15px] outline-none focus:border-accent focus:shadow-[0_0_0_4px_var(--tint)]" />
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
                <b className="text-ink">{h.who}</b> · {h.what} · {fmtDateTime(h.at)}
              </li>
            ))}
          </ol>
        </Section>
      )}

      {/* 아래 고정 행동 칸 */}
      {isOpen && !reportOnly && (
        <div data-bottom-bar className={`glass fixed inset-x-0 z-20 ${director ? "bottom-0 pb-[max(12px,env(safe-area-inset-bottom))]" : "bottom-[calc(64px+env(safe-area-inset-bottom))]"} bg-bar px-4 py-3 shadow-[0_-1px_0_var(--sep)] backdrop-blur-xl backdrop-saturate-[1.8] lg:sticky lg:bottom-4 lg:mx-0 lg:rounded-2xl lg:shadow-[0_8px_30px_rgba(11,31,58,.12),0_0_0_.5px_var(--sep)]`}>
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

      {/* 상담: '시간 거절'은 이유를 남기고 새 시간을 받는다(reject), '상담 거절'은 상담 자체를 받지 않는다(dismiss, 이유가 학부모에게 보임) */}
      <Sheet open={sheet === "reject_time"} onClose={() => setSheet(null)} title="이 시간을 거절할까요?">
        <p className="text-sub text-ink2">고른 이유는 다음 시간 제안에 반영돼요. 학부모가 새 시간을 다시 골라요.</p>
        <ReasonChips options={["연장반 당번", "전화로 충분"]} value={reason} onChange={setReason} />
        <Button variant="danger" loading={act.isPending} lockedReason={reason ? undefined : "이유를 고르면 거절할 수 있어요"} onClick={() => run({ action: "reject_time", reason }, { title: "시간을 거절했어요", sub: reason })}>거절하기</Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>취소</Button>
      </Sheet>

      <Sheet open={sheet === "reject"} onClose={() => setSheet(null)} title={c.type === "consult" ? "이 상담을 거절할까요?" : "이 요청을 거절할까요?"}>
        <p className="text-sub text-ink2">{c.type === "consult" ? "상담을 받지 않는 경우예요. 고른 이유가 학부모에게 보여요." : "고른 이유가 학부모에게 함께 전달돼요."}</p>
        <ReasonChips options={["개인정보 요청", "원 운영 범위 밖", "중복 요청"]} value={reason} onChange={setReason} />
        <Button variant="danger" loading={act.isPending} lockedReason={reason ? undefined : "이유를 고르면 거절할 수 있어요"} onClick={() => run({ action: "reject", reason }, { title: "거절했어요", sub: reason })}>거절하기</Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>취소</Button>
      </Sheet>

      <Sheet open={sheet === "hold"} onClose={() => setSheet(null)} title="언제까지 보류할까요?">
        <p className="text-sub text-ink2">학부모에게는 예정일만 보이고, 이유는 교직원끼리만 봐요.</p>
        <ReasonChips options={["원장님 확인 필요", "자료 확인 중", "학부모 통화 예정"]} value={reason} onChange={setReason} />
        <ReasonChips options={holdDates} value={text} onChange={setText} />
        <Button loading={act.isPending} lockedReason={reason && text ? undefined : "이유와 예정일을 골라 주세요"} onClick={() => run({ action: "hold", reason, until: text }, { title: "보류했어요", sub: `${text}까지` })}>보류하기</Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>취소</Button>
      </Sheet>

      <Sheet open={sheet === "complete"} onClose={() => setSheet(null)} title="이 민원을 완료할까요?">
        <p className="text-sub text-ink2">학부모가 {c.parentConfirmedAt ? "확인했어요" : "아직 확인하지 않았어요"}. 완료하면 학부모 화면에 '완료'로 보여요.</p>
        {!c.parentConfirmedAt && <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={3} placeholder="학부모 확인 전 완료하는 이유" className="rounded-xl bg-g px-3.5 py-3 text-[15px] outline-none" />}
        <Button loading={act.isPending} lockedReason={!c.parentConfirmedAt && !reason.trim() ? "완료 이유를 적어 주세요" : undefined} onClick={() => run({ action: "complete", reason: reason.trim() || undefined }, { title: "처리 완료했어요", sub: "완료 필터로 옮겼어요" })}>처리 완료</Button>
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

      <Sheet open={sheet === "reclassify"} onClose={() => setSheet(null)} title="긴급 사유를 골라 주세요">
        <ReasonChips options={["아이 안전", "교직원 위협", "법적·외부기관", "개인정보 유출"]} value={text} onChange={setText} />
        <Button loading={act.isPending} lockedReason={text ? undefined : "긴급 사유를 골라 주세요"} onClick={() => {
          const categories = { "아이 안전": "child_safety", "교직원 위협": "staff_attack", "법적·외부기관": "legal_external", "개인정보 유출": "privacy_leak" } as const;
          run({ action: "reclassify", risk: "urgent", riskCategory: categories[text as keyof typeof categories], reason: `담임 판단 · ${text}` }, { title: "긴급으로 분류했어요", sub: "원장님께도 알렸어요" });
        }}>긴급으로 분류</Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>취소</Button>
      </Sheet>
    </article>
  );
}

function TeacherActions({ c, open, draft, slot, pending, run }: { c: Card; open: (k: SheetKind) => void; draft: string; slot: string; pending: boolean; run: (b: CardAction, ok: { title: string; sub?: string }) => void }) {
  if (c.kind === "rule_proposal" && c.rule) return <RuleActions c={c} />;
  if (c.status === "on_hold")
    return (
      <>
        <p className="text-center text-sub text-ink2">보류 중인 요청이에요. 다시 확인하려면 재개해 주세요</p>
        <Button loading={pending} onClick={() => run({ action: "resume" }, { title: "다시 확인 필요로 옮겼어요", sub: "받은함의 확인 필요에서 볼 수 있어요" })}>재개하기</Button>
      </>
    );
  if (c.risk === "judge")
    return (
      <>
        <p className="text-center text-sub text-ink2">일반이나 긴급으로 다시 분류해 주세요</p>
        <div className="grid grid-cols-2 gap-2">
          <Button variant="tinted" loading={pending} onClick={() => run({ action: "reclassify", risk: "normal", reason: "담임 판단" }, { title: "일반으로 분류했어요", sub: "확인 필요로 옮겼어요" })}>일반으로</Button>
          <Button variant="navy" loading={pending} onClick={() => open("reclassify")}>긴급으로</Button>
        </div>
      </>
    );
  if (c.status === "sent_or_booked" && (c.parentConfirmedAt || c.type === "complaint"))
    return <Button icon="approve" onClick={() => open("complete")}>처리 완료</Button>;
  if (c.type === "consult")
    return (
      <div className="grid grid-cols-[1fr_1fr_2fr] gap-2">
        <Button variant="gray" size="sm" onClick={() => open("reject_time")}>시간 거절</Button>
        <Button variant="gray" size="sm" onClick={() => open("reject")}>상담 거절</Button>
        <Button onClick={() => open("confirm_slot")} lockedReason={slot ? undefined : "확정할 시간을 골라 주세요"}>확정하기</Button>
      </div>
    );
  return (
    <>
      <div className="grid grid-cols-3 gap-2">
        <Button variant="gray" size="sm" onClick={() => open("hold")}>보류</Button>
        <Button variant="gray" size="sm" onClick={() => open("reject")}>거절</Button>
        <Button variant="gray" size="sm" loading={pending} disabled={c.escalated} onClick={() => run({ action: "escalate" }, { title: "원장님께 올렸어요" })}>{c.escalated ? "원장 보고됨" : "원장님께 보고"}</Button>
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
        <Button variant="tinted" lockedReason="준비 중이에요">재배정</Button>
        <Button onClick={() => open("note")}>{c.directorNote ? "지시 고치기" : "지시 남기기"}</Button>
      </div>
    </>
  );
}

/** 개인 규칙 제안 카드의 켜기·거절 (API 20) */
function RuleActions({ c }: { c: Card }) {
  const decide = useRuleDecision();
  const toast = useToast();
  const go = (decision: "activate" | "decline") =>
    decide.mutate(
      { ruleId: c.rule!.id, decision },
      {
        onSuccess: () => toast({ kind: "ok", title: decision === "activate" ? "규칙을 켰어요" : "제안을 거절했어요", sub: decision === "activate" ? "AI가 참고할 수 있어요" : "같은 이유로 세 번 더 거절하면 다시 제안해요" }),
        onError: (e) => toast({ kind: "error", title: e instanceof ApiError && e.status === 409 ? "이미 처리한 제안이에요" : "처리하지 못했어요", sub: e instanceof ApiError && e.status === 409 ? undefined : "연결을 확인하고 다시 눌러 주세요" }),
      },
    );
  return (
    <div className="grid grid-cols-[1fr_2fr] gap-2">
      <Button variant="gray" loading={decide.isPending} onClick={() => go("decline")}>거절</Button>
      <Button loading={decide.isPending} onClick={() => go("activate")}>규칙 켜기</Button>
    </div>
  );
}
