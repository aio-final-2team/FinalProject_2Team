import { useState } from "react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import { useNoteReply, useSuppliesCheck } from "@/api/notes";
import { Button } from "@/components/Button";
import { Sheet } from "@/components/Sheet";
import { useToast } from "@/components/Toast";
import type { DailyNote } from "@/domain/notes";
import { PARENT_LABEL, type Status } from "@/domain/status";

const hm = (iso: string) => new Date(iso).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false });

/** 보낸 알림장 아래: 준비물 챙겼어요(API 68), 선생님께 답장하기(API 62)와 보낸 답장 */
export function NoteReply({ note }: { note: DailyNote }) {
  const reply = useNoteReply(note.id);
  const supplies = useSuppliesCheck(note.id);
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const hasSupplies = note.content.items.some((i) => i.key === "supplies" && i.value.trim());
  const checkedAt = note.supplies_checked_at;
  const replies = note.replies ?? [];

  const check = () =>
    supplies.mutate(undefined, {
      onSuccess: () => toast({ kind: "ok", title: "준비물을 챙겼다고 알렸어요" }),
      onError: () => toast({ kind: "error", title: "표시하지 못했어요", sub: "연결을 확인하고 다시 눌러 주세요" }),
    });

  const send = () =>
    reply.mutate(text.trim(), {
      onSuccess: () => {
        setOpen(false);
        setText("");
        toast({ kind: "ok", title: "답장을 보냈어요", sub: "선생님이 확인하고 답해 드려요" });
      },
      onError: (e) => {
        const s = e instanceof ApiError ? e.status : 0;
        toast({ kind: "error", title: s === 403 ? "먼저 필수 동의가 필요해요" : "답장을 보내지 못했어요", sub: s === 403 ? "내 정보에서 동의를 확인해 주세요" : "내용은 그대로 두었어요. 다시 눌러 주세요" });
      },
    });

  return (
    <div className="border-t border-sep px-5 py-4">
      <div className="flex flex-wrap items-center gap-2">
        {hasSupplies &&
          (checkedAt ? (
            <span className="inline-flex h-10 items-center rounded-full bg-tint px-4 text-footnote font-bold text-accent-ink">준비물 챙겼어요 · {hm(checkedAt)}</span>
          ) : (
            <Button variant="tinted" size="sm" loading={supplies.isPending} onClick={check}>준비물 챙겼어요</Button>
          ))}
        <Button variant="gray" size="sm" onClick={() => setOpen(true)}>선생님께 답장하기</Button>
      </div>

      {replies.length > 0 && (
        <section aria-label="보낸 답장" className="mt-3 grid gap-2">
          <h3 className="text-footnote font-semibold text-ink2">보낸 답장</h3>
          <ul className="overflow-hidden rounded-xl bg-g [&>li+li]:border-t [&>li+li]:border-sep">
            {replies.map((r) => (
              <li key={r.request_id}>
                <Link to={`/parent/requests/${r.request_id}`} className="block px-3.5 py-2.5 active:bg-fill">
                  <p className="text-callout leading-relaxed">{r.body}</p>
                  <p className="mt-0.5 text-footnote text-ink2"><span className="font-bold text-lav">{PARENT_LABEL[r.status as Status]?.label ?? "접수됨"}</span> · {hm(r.created_at)}</p>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      <Sheet open={open} onClose={() => setOpen(false)} title="선생님께 답장하기">
        <p className="text-sub text-ink2">보낸 답장은 문의로 접수돼요. 선생님이 확인한 뒤 답해 드려요.</p>
        <label className="grid gap-1.5">
          <span className="text-footnote font-semibold">답장 내용</span>
          <textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} rows={4} placeholder="예: 내일 준비물은 무엇인가요?" className="rounded-md border-[1.5px] border-line bg-card p-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
        </label>
        <Button loading={reply.isPending} lockedReason={text.trim() ? undefined : "내용을 적어 주세요"} onClick={send}>보내기</Button>
        <Button variant="plain" size="sm" onClick={() => setOpen(false)}>닫기</Button>
      </Sheet>
    </div>
  );
}
