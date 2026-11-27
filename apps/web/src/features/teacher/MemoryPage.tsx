import { useState } from "react";
import { ApiError } from "@/api/client";
import { KIND_LABEL, REASON_LABEL, isDeletable, statusOf, useConfirmMemory, useDeleteMemory, useMemories, useRuleDecision, useSavedAnswerStatus, type Memory, type MemoryKind } from "@/api/memory";
import { Button } from "@/components/Button";
import { QueryState } from "@/components/QueryState";
import { ScreenTop } from "@/components/ScreenTop";
import { Sheet } from "@/components/Sheet";
import { StateView } from "@/components/StateView";
import { useToast } from "@/components/Toast";
import type { Role } from "@/domain/types";

/** 역할마다 보이는 종류와 순서. 학부모는 돌봄 메모와 선호, 교사·원장은 승인한 답·규칙·말투·선호·거절한 이유 */
const ORDER: Record<Role, MemoryKind[]> = {
  parent: ["care_note", "preference"],
  teacher: ["saved_answer", "rule", "tone", "preference", "rejection_reason"],
  director: ["saved_answer", "rule", "tone", "preference", "rejection_reason"],
};
const BACK: Record<Role, { to: string; label: string }> = {
  parent: { to: "/parent/home", label: "홈" },
  teacher: { to: "/teacher/home", label: "홈" },
  director: { to: "/director/overview", label: "현황" },
};
const SUB: Record<Role, string> = {
  parent: "확인하신 내용만 AI가 참고해요. 언제든 지울 수 있어요",
  teacher: "AI가 내 결정에서 배운 것이에요. 아이 이름은 가려서 저장돼요",
  director: "AI가 내 결정에서 배운 것이에요. 아이 이름은 가려서 저장돼요",
};
const SAVED_STATUS: Record<string, string> = { active: "쓰는 중", off: "꺼짐" };
const RULE_STATUS: Record<string, string> = { active: "켜짐", proposed: "제안", pending: "제안", off: "꺼짐", declined: "꺼짐" };
const when = (iso: string) => new Date(iso).toLocaleDateString("ko-KR", { month: "long", day: "numeric" });

/** 내 AI 기억 (API 31). 세 역할이 자기 것만 보고 지운다. 돌봄 메모는 보호자가 확인한 것만 쓰인다 */
const SHOW = 5;
/** 규칙 제목이 "상담 · 답변 규칙"처럼 모두 같으면 구분이 안 된다. 그때는 규칙 내용의 첫 부분을 제목으로 쓴다 */
const ruleHead = (m: { title?: string; content: string }) => {
  if (m.title && !/답변 규칙$/.test(m.title)) return m.title;
  const first = m.content.split(/[.。!?\n]/)[0].trim();
  return first.length > 24 ? `${first.slice(0, 24)}…` : first || m.title;
};

export function MemoryPage({ role = "teacher" }: { role?: Role }) {
  const q = useMemories();
  const del = useDeleteMemory();
  const confirm = useConfirmMemory();
  const saved = useSavedAnswerStatus();
  const rule = useRuleDecision();
  const toast = useToast();
  const [target, setTarget] = useState<Memory | null>(null);
  /* 기억하지 않기로 한 것은 내용이 비어 있으므로 보이지 않는다 */
  const items = (q.data ?? []).filter((m) => m.confirm_status !== "discarded" && (m.content || m.kind === "rule"));
  /* 한 묶음에 기억이 많으면 처음 몇 개만 펼치고 나머지는 더 보기로 연다 */
  const [more, setMore] = useState<Record<string, boolean>>({});
  const groups = ORDER[role].map((k) => ({ kind: k, rows: items.filter((m) => m.kind === k) })).filter((g) => g.rows.length);
  /* 서버가 아직 이 역할에 기억을 열지 않았으면(403) 오류 대신 준비 중으로 안내한다 */
  const notOpen = q.error instanceof ApiError && q.error.status === 403;
  const failed = (title: string) => toast({ kind: "error", title, sub: "연결을 확인하고 다시 눌러 주세요" });

  const remove = () => {
    if (!target || typeof target.id !== "number") return;
    del.mutate(target.id, {
      onSuccess: () => { setTarget(null); toast({ kind: "ok", title: "기억을 지웠어요" }); },
      onError: (e) => { setTarget(null); if (e instanceof ApiError && e.status === 404) toast({ kind: "error", title: "이미 지워진 기억이에요" }); else failed("지우지 못했어요"); },
    });
  };
  const decide = (m: Memory, decision: "remember" | "discard") =>
    typeof m.id === "number" &&
    confirm.mutate({ id: m.id, decision }, {
      onSuccess: () => toast({ kind: "ok", title: decision === "remember" ? "기억했어요" : "기억하지 않았어요" }),
      onError: () => failed("처리하지 못했어요"),
    });
  const toggle = (m: Memory) => {
    const next = statusOf(m) === "off" ? "active" : "off";
    saved.mutate({ id: String(m.id), status: next }, { onSuccess: () => toast({ kind: "ok", title: next === "off" ? "껐어요" : "켰어요" }), onError: () => failed("바꾸지 못했어요") });
  };
  const turnRuleOff = (m: Memory) => {
    rule.mutate(
      { ruleId: String(m.id), decision: "off" },
      { onSuccess: () => toast({ kind: "ok", title: "규칙을 껐어요" }), onError: () => failed("규칙을 끄지 못했어요") },
    );
  };

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop audience={role === "parent" ? "parent" : "staff"} back={BACK[role]} title="내 AI 기억" sub={SUB[role]} />
      {notOpen ? (
        <div className="mt-6"><StateView kind="empty" audience={role === "parent" ? "parent" : "staff"} title="준비 중이에요" sub={"열리면 알려 드릴게요"} /></div>
      ) : (
        <QueryState queries={[q]} skeleton={3} errorTitle="기억을 불러오지 못했어요">
          {groups.length === 0 ? (
            <div className="mt-6">
              <StateView
                kind="empty"
                audience={role === "parent" ? "parent" : "staff"}
                title="아직 기억한 내용이 없어요"
                sub={role === "parent" ? "요청에서 알려 주신 내용은\n확인하신 뒤에만 기억해요" : "카드를 거절하면\n그 이유가 여기에 쌓여요"}
              />
            </div>
          ) : (
            groups.map((g) => (
              <section key={g.kind} className="mt-5" aria-label={KIND_LABEL[g.kind]}>
                <h2 className="mb-2 px-1 text-footnote font-semibold text-ink2">{KIND_LABEL[g.kind]} {g.rows.length}</h2>
                <ul className="overflow-hidden rounded-lg bg-card shadow-card [&>li+li]:border-t [&>li+li]:border-sep">
                  {(more[g.kind] ? g.rows : g.rows.slice(0, SHOW)).map((m) => {
                    const pending = m.kind === "care_note" && m.confirm_status === "pending";
                    const state = m.kind === "saved_answer" ? SAVED_STATUS[statusOf(m) ?? ""] : m.kind === "rule" ? RULE_STATUS[statusOf(m) ?? ""] : undefined;
                    const head = m.kind === "care_note" ? (m.title ?? `${m.child_name ?? "아이"} 돌봄 메모`) : m.kind === "rule" ? ruleHead(m) : m.kind === "saved_answer" ? m.title : undefined;
                    return (
                      <li key={String(m.id)} className="flex items-start gap-3 px-3 py-3">
                        <span className="min-w-0 flex-1">
                          {head && <b className="block break-keep text-callout font-semibold">{head}</b>}
                          {!head && m.reason_code && (REASON_LABEL[m.reason_code] ?? m.reason_code) !== m.content && <b className="block text-caption font-bold text-accent-ink">{REASON_LABEL[m.reason_code] ?? m.reason_code}</b>}
                          <span className="block break-keep text-callout text-ink">{m.content}</span>
                          <span className="mt-0.5 flex items-center gap-2 text-caption text-ink2">
                            <time>{when(m.confirmed_at ?? m.created_at)}</time>
                            {pending && <b className="font-bold text-lav">확인 필요</b>}
                            {state && <b className="font-bold">{state}</b>}
                          </span>
                          {pending && (
                            <span className="mt-2 flex gap-2">
                              <button type="button" disabled={confirm.isPending} onClick={() => decide(m, "remember")} className="h-9 rounded-md bg-tint px-3 text-footnote font-semibold text-accent-ink active:scale-[.97] disabled:opacity-50">기억하기</button>
                              <button type="button" disabled={confirm.isPending} onClick={() => decide(m, "discard")} className="h-9 rounded-md bg-fill px-3 text-footnote font-semibold text-ink active:scale-[.97] disabled:opacity-50">기억하지 않기</button>
                            </span>
                          )}
                        </span>
                        {isDeletable(m) && !pending && (
                          <button type="button" onClick={() => setTarget(m)} aria-label="이 기억 지우기" className="h-9 shrink-0 rounded-md px-2.5 text-footnote font-semibold text-ink2 active:scale-[.97]">지우기</button>
                        )}
                        {m.kind === "saved_answer" && (
                          <button type="button" disabled={saved.isPending} onClick={() => toggle(m)} className="h-9 shrink-0 rounded-md px-2.5 text-footnote font-semibold text-ink2 active:scale-[.97] disabled:opacity-50">{statusOf(m) === "off" ? "켜기" : "끄기"}</button>
                        )}
                        {m.kind === "rule" && statusOf(m) === "active" && (
                          <button type="button" disabled={rule.isPending} onClick={() => turnRuleOff(m)} className="h-9 shrink-0 rounded-md px-2.5 text-footnote font-semibold text-ink2 active:scale-[.97] disabled:opacity-50">끄기</button>
                        )}
                      </li>
                    );
                  })}
                </ul>
                {g.rows.length > SHOW && (
                  <button type="button" onClick={() => setMore((p) => ({ ...p, [g.kind]: !p[g.kind] }))} className="mt-1.5 inline-flex min-h-9 items-center px-1 text-footnote font-semibold text-accent-ink active:scale-[.97]">
                    {more[g.kind] ? "접기" : `나머지 ${g.rows.length - SHOW}개 더 보기`}
                  </button>
                )}
              </section>
            ))
          )}
        </QueryState>
      )}
      <Sheet open={!!target} onClose={() => setTarget(null)} title="이 기억을 지울까요?">
        <p className="text-footnote text-ink2">지우면 AI가 더 이상 이 내용을 참고하지 않아요.</p>
        {target && <p className="rounded-md bg-g p-3 text-callout">{target.content}</p>}
        <Button variant="danger" loading={del.isPending} onClick={remove}>지우기</Button>
        <Button variant="plain" size="sm" onClick={() => setTarget(null)}>취소</Button>
      </Sheet>
    </div>
  );
}
