import { useState, type FormEvent } from "react";
import { Buddy } from "@/components/Brand";
import { Icon } from "@/components/Icon";
import { ScreenTop } from "@/components/ScreenTop";

type Message = { id: number; from: "ai" | "me"; text: string };

const QUICK = ["오늘 알림장 보여줘", "내일 귀가 요청할래", "준비물이 뭐야?"];

/** API를 붙이기 전 학부모 AI 대화 UX만 확인하는 독립 UI. */
export function ParentAiPage() {
  const [text, setText] = useState("");
  const [messages, setMessages] = useState<Message[]>([
    { id: 1, from: "ai", text: "안녕하세요! 무엇을 도와드릴까요? 편하게 말씀해 주세요." },
  ]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const value = text.trim();
    if (!value) return;
    const now = Date.now();
    setMessages((prev) => [
      ...prev,
      { id: now, from: "me", text: value },
      { id: now + 1, from: "ai", text: "아직 AI와 연결하기 전이에요. 지금은 대화 화면만 미리 볼 수 있어요." },
    ]);
    setText("");
  };

  return (
    <div className="mx-auto flex min-h-[calc(100dvh-76px)] max-w-[680px] flex-col px-4 pb-4 lg:min-h-dvh lg:pb-6">
      <ScreenTop audience="parent" back={{ to: "/parent/home", label: "홈" }} title="AI 도우미" sub="편하게 말하면 필요한 기능을 찾아드려요" />

      <div className="mt-3 flex items-center gap-2 rounded-xl bg-tint px-3 py-2 text-footnote font-semibold text-accent-ink">
        <Icon name="ai" className="size-4" />
        UI 미리보기 · 입력한 내용은 아직 전송되지 않아요
      </div>

      <div className="flex-1 py-5" aria-live="polite">
        <div className="grid gap-3">
          {messages.map((message) => (
            <div key={message.id} className={`flex items-end gap-2 ${message.from === "me" ? "justify-end" : "justify-start"}`}>
              {message.from === "ai" && <Buddy face="basic" small className="size-8" />}
              <p className={`max-w-[82%] rounded-2xl px-3.5 py-2.5 text-callout leading-relaxed shadow-card ${message.from === "me" ? "rounded-br-sm bg-brand-fill text-on-brand" : "rounded-bl-sm bg-card text-ink"}`}>
                {message.text}
              </p>
            </div>
          ))}
        </div>

        {messages.length === 1 && (
          <div className="mt-5 flex flex-wrap gap-2">
            {QUICK.map((q) => (
              <button key={q} type="button" onClick={() => setText(q)} className="rounded-full border border-sep bg-card px-3 py-2 text-footnote font-semibold text-ink transition-transform duration-100 active:scale-[.97]">
                {q}
              </button>
            ))}
          </div>
        )}
      </div>

      <form onSubmit={submit} className="sticky bottom-[76px] flex items-end gap-2 rounded-2xl border border-sep bg-card p-2 shadow-float lg:bottom-4">
        <label htmlFor="parent-ai-input" className="sr-only">물어볼 내용</label>
        <textarea
          id="parent-ai-input"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              e.currentTarget.form?.requestSubmit();
            }
          }}
          rows={1}
          placeholder="예: 내일 할머니가 데리러 가요"
          className="max-h-28 min-h-11 flex-1 resize-none bg-transparent px-2 py-2.5 text-callout outline-none placeholder:text-ink3"
        />
        <button type="submit" disabled={!text.trim()} aria-label="보내기" className="grid size-11 shrink-0 place-items-center rounded-xl bg-brand-fill text-on-brand transition-transform duration-100 active:scale-[.96] disabled:bg-fill2 disabled:text-ink2">
          <Icon name="send" className="size-5" />
        </button>
      </form>
    </div>
  );
}
