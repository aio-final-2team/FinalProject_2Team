import { useConfirmMemory } from "@/api/memory";
import type { RequestDetail } from "@/api/requests";
import { useToast } from "@/components/Toast";

/** 요청 상세의 돌봄 메모 확인(서버 #377 memory_candidates). 보호자가 확인하기 전에는 AI가 어디에도 쓰지 않는다 */
export function MemoryCandidates({ items }: { items: NonNullable<RequestDetail["memory_candidates"]> }) {
  const confirm = useConfirmMemory();
  const toast = useToast();
  if (!items.length) return null;
  const decide = (id: number, decision: "remember" | "discard") =>
    confirm.mutate({ id, decision }, {
      onSuccess: () => toast({ kind: "ok", title: decision === "remember" ? "기억했어요" : "기억하지 않았어요" }),
      onError: () => toast({ kind: "error", title: "처리하지 못했어요", sub: "연결을 확인하고 다시 눌러 주세요" }),
    });
  return (
    <section className="mt-4 rounded-lg bg-lav-tint p-4" aria-label="기억해 둘까요?">
      <h2 className="text-callout font-bold">이 내용을 기억해 둘까요?</h2>
      <p className="mt-1 text-footnote text-ink2">기억하면 이후 답변과 알림장에 참고해요. 기억하지 않으면 바로 지워요.</p>
      <ul className="mt-3 grid gap-3">
        {items.map((c) => (
          <li key={c.id} className="rounded-md bg-card p-3">
            <b className="block text-caption font-bold text-accent-ink">{c.child_name}</b>
            <span className="block break-keep text-callout">{c.content}</span>
            <span className="mt-2 flex gap-2">
              <button type="button" disabled={confirm.isPending} onClick={() => decide(c.id, "remember")} className="h-10 rounded-md bg-brand-fill px-4 text-footnote font-semibold text-on-brand active:scale-[.97] disabled:opacity-50">기억하기</button>
              <button type="button" disabled={confirm.isPending} onClick={() => decide(c.id, "discard")} className="h-10 rounded-md bg-fill px-4 text-footnote font-semibold text-ink active:scale-[.97] disabled:opacity-50">기억하지 않기</button>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
