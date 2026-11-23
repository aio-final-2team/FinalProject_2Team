import { useState } from "react";
import { PrimaryButton, SubButton } from "@/components/Dock";
import { Sheet } from "@/components/Sheet";
import type { RecordEntry } from "./store";

const QUICK = ["점심 다 먹음", "점심 반 남김", "낮잠 짧음", "친구 도와줌", "블록놀이 집중", "컨디션 좋음"];

/** A-02 한 줄 기록 시트: 빠른 버튼 + 한 줄 (디자인 시스템 7.13 시트) */
export function RecordSheet({ name, entries, open, onClose, onSave, onRemove }: { name: string; entries: RecordEntry[]; open: boolean; onClose: () => void; onSave: (text: string) => void; onRemove?: (index: number) => void }) {
  const [picked, setPicked] = useState<string[]>([]);
  const [text, setText] = useState("");
  const close = () => {
    setPicked([]);
    setText("");
    onClose();
  };
  const save = () => {
    const t = [...picked, text.trim()].filter(Boolean).join(", ");
    if (!t) return;
    onSave(t);
    close();
  };
  return (
    <Sheet open={open} onClose={close} title={`${name} 기록 남기기`}>
      {entries.length ? (
        <ul className="overflow-hidden rounded-md bg-g" aria-label="오늘 기록">
          {entries.map((e, i) => (
            <li key={`${e.at}-${i}`} className="flex items-center gap-2 border-b border-sep px-3 py-2 text-footnote last:border-0">
              <span className="shrink-0 tabular-nums text-ink2">{e.at}</span>
              <span className="min-w-0 flex-1">{e.text}</span>
              {onRemove && (
                <button type="button" onClick={() => onRemove(i)} className="h-8 shrink-0 rounded-md px-2 font-semibold text-ink2 active:scale-[.97]" aria-label={`${e.at} 기록 삭제`}>
                  삭제
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-footnote text-ink2">오늘 아직 기록이 없어요</p>
      )}
      <div className="flex flex-wrap gap-2" role="group" aria-label="빠른 기록">
        {QUICK.map((q) => {
          const on = picked.includes(q);
          return (
            <button
              key={q}
              type="button"
              aria-pressed={on}
              onClick={() => setPicked((p) => (on ? p.filter((x) => x !== q) : [...p, q]))}
              className={`h-9 rounded-full border px-3 text-footnote font-semibold transition-colors ${on ? "border-accent bg-tint text-accent-ink" : "border-sep bg-card text-ink"}`}
            >
              {q}
            </button>
          );
        })}
      </div>
      <label className="grid gap-1.5">
        <span className="text-footnote font-semibold">한 줄 기록</span>
        <input
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => !text && setText("블록으로 높은 탑을 쌓으며 집중했어요")}
          onKeyDown={(e) => e.key === "Enter" && save()}
          placeholder="예: 블록으로 탑을 높이 쌓음"
          maxLength={200}
          className="h-12 rounded-md border-[1.5px] border-line bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]"
        />
      </label>
      <div className="grid grid-cols-[1fr_2fr] gap-2">
        <SubButton tone="gray" className="h-[52px]" onClick={close}>
          닫기
        </SubButton>
        <PrimaryButton onClick={save} disabled={!picked.length && !text.trim()}>
          기록 남기기
        </PrimaryButton>
      </div>
    </Sheet>
  );
}
