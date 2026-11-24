import { useState } from "react";
import { ApiError } from "@/api/client";
import { useCorrectNote } from "@/api/notes";
import { PrimaryButton, SubButton } from "@/components/Dock";
import { Sheet } from "@/components/Sheet";
import { useToast } from "@/components/Toast";
import type { DailyNote, NoteItem } from "@/domain/notes";

/** 보낸 알림장 정정 (API 52). 고친 내용 전체와 사유를 보내고, 보호자에게 정정 알림이 간다 */
export function CorrectSheet({ note, open, onClose, cid, date }: { note: DailyNote; open: boolean; onClose: () => void; cid?: string; date: string }) {
  const correct = useCorrectNote(cid, date);
  const toast = useToast();
  const [items, setItems] = useState<NoteItem[]>(note.content.items);
  const [reason, setReason] = useState("");
  const changed = items.some((it, i) => it.value !== note.content.items[i]?.value);
  const submit = () =>
    correct.mutate(
      { id: note.id, version: note.version ?? 1, items, reason_text: reason.trim() },
      {
        onSuccess: () => { onClose(); setReason(""); toast({ kind: "ok", title: "정정했어요", sub: "보호자에게 정정 알림이 가요" }); },
        onError: (e) => {
          const conflict = e instanceof ApiError && e.status === 409;
          toast({ kind: "error", title: conflict ? "알림장이 방금 바뀌었어요" : "정정하지 못했어요", sub: conflict ? "최신 내용으로 다시 불러왔어요.\n확인하고 다시 눌러 주세요" : "연결을 확인하고 다시 눌러 주세요", ...(conflict ? {} : { action: { label: "다시 시도", run: submit } }) });
          if (conflict) onClose();
        },
      },
    );
  return (
    <Sheet open={open} onClose={onClose} title="보낸 알림장 정정">
      <p className="text-footnote text-ink2">잘못된 내용을 고치면 보호자 화면이 바뀌고 정정 알림이 가요.</p>
      <div className="grid max-h-[40dvh] gap-3 overflow-y-auto">
        {items.map((it, i) => (
          <label key={`${it.key}-${i}`} className="grid gap-1.5">
            <span className="text-footnote font-semibold">{it.label}</span>
            <textarea value={it.value} rows={2} onChange={(e) => setItems((xs) => xs.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} className="rounded-md border-[1.5px] border-line bg-card px-3 py-2 text-callout outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
          </label>
        ))}
      </div>
      <label className="grid gap-1.5">
        <span className="text-footnote font-semibold">정정 사유 <span className="font-normal text-ink2">(교직원만 볼 수 있어요)</span></span>
        <input value={reason} maxLength={500} onChange={(e) => setReason(e.target.value)} placeholder="예: 활동 기록 오기" className="h-12 rounded-md border-[1.5px] border-line bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
      </label>
      <div className="grid grid-cols-[1fr_2fr] gap-2">
        <SubButton tone="gray" className="h-[52px]" onClick={onClose}>닫기</SubButton>
        <PrimaryButton loading={correct.isPending} disabled={!changed || !reason.trim()} onClick={submit}>정정하기</PrimaryButton>
      </div>
    </Sheet>
  );
}
