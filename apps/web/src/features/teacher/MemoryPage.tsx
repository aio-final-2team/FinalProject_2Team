import { useState } from "react";
import { ApiError } from "@/api/client";
import { KIND_LABEL, REASON_LABEL, useDeleteMemory, useMemories, type Memory, type MemoryKind } from "@/api/memory";
import { Button } from "@/components/Button";
import { QueryState } from "@/components/QueryState";
import { ScreenTop } from "@/components/ScreenTop";
import { Sheet } from "@/components/Sheet";
import { StateView } from "@/components/StateView";
import { useToast } from "@/components/Toast";

const ORDER: MemoryKind[] = ["rejection_reason", "preference", "tone"];
const when = (iso: string) => new Date(iso).toLocaleDateString("ko-KR", { month: "long", day: "numeric" });

/** 내 AI 기억 (API 31). AI가 내 결정에서 배운 것을 보고 지울 수 있다. 아이 이름은 가려서 저장된다 */
export function MemoryPage() {
  const q = useMemories();
  const del = useDeleteMemory();
  const toast = useToast();
  const [target, setTarget] = useState<Memory | null>(null);
  const items = q.data ?? [];
  const groups = ORDER.map((k) => ({ kind: k, rows: items.filter((m) => m.kind === k) })).filter((g) => g.rows.length);

  const remove = () => {
    if (!target) return;
    del.mutate(target.id, {
      onSuccess: () => { setTarget(null); toast({ kind: "ok", title: "기억을 지웠어요" }); },
      onError: (e) => { setTarget(null); toast({ kind: "error", title: e instanceof ApiError && e.status === 404 ? "이미 지워진 기억이에요" : "지우지 못했어요", sub: e instanceof ApiError && e.status === 404 ? undefined : "연결을 확인하고 다시 눌러 주세요" }); },
    });
  };

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop back={{ to: "/teacher/home", label: "홈" }} title="내 AI 기억" sub="AI가 내 결정에서 배운 것이에요. 아이 이름은 가려서 저장돼요" />
      <QueryState queries={[q]} skeleton={3} errorTitle="기억을 불러오지 못했어요">
        {groups.length === 0 ? (
          <div className="mt-6"><StateView kind="empty" audience="staff" title="아직 배운 기억이 없어요" sub={"카드를 반려하거나 거절하면\n그 이유가 여기에 쌓여요"} /></div>
        ) : (
          groups.map((g) => (
            <section key={g.kind} className="mt-5" aria-label={KIND_LABEL[g.kind]}>
              <h2 className="mb-2 px-1 text-footnote font-semibold text-ink2">{KIND_LABEL[g.kind]} {g.rows.length}</h2>
              <ul className="overflow-hidden rounded-lg bg-card shadow-card [&>li+li]:border-t [&>li+li]:border-sep">
                {g.rows.map((m) => (
                  <li key={m.id} className="flex items-start gap-3 px-3 py-3">
                    <span className="min-w-0 flex-1">
                      {m.reason_code && (REASON_LABEL[m.reason_code] ?? m.reason_code) !== m.content && <b className="block text-caption font-bold text-accent-ink">{REASON_LABEL[m.reason_code] ?? m.reason_code}</b>}
                      <span className="block break-keep text-callout">{m.content}</span>
                      <time className="text-caption text-ink2">{when(m.created_at)}</time>
                    </span>
                    <button type="button" onClick={() => setTarget(m)} aria-label="이 기억 지우기" className="h-9 shrink-0 rounded-md px-2.5 text-footnote font-semibold text-ink2 active:scale-[.97]">지우기</button>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </QueryState>
      <Sheet open={!!target} onClose={() => setTarget(null)} title="이 기억을 지울까요?">
        <p className="text-footnote text-ink2">지우면 AI가 더 이상 이 내용을 참고하지 않아요.</p>
        {target && <p className="rounded-md bg-g p-3 text-callout">{target.content}</p>}
        <Button variant="danger" loading={del.isPending} onClick={remove}>지우기</Button>
        <Button variant="plain" size="sm" onClick={() => setTarget(null)}>취소</Button>
      </Sheet>
    </div>
  );
}
