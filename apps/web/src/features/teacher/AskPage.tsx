import { useRef, useState } from "react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import { useStaffAsk, type StaffAnswer } from "@/api/staff";
import { Button } from "@/components/Button";
import { Markdown } from "@/components/Markdown";
import { ScreenTop } from "@/components/ScreenTop";
import { useToast } from "@/components/Toast";

type Turn = { q: string; a: StaffAnswer };
const MAX = 2000;
const EXAMPLES = ["다음 달 현장학습 준비물이 뭐예요?", "이번 주 급식에 알레르기 식재료가 있나요?"];

/** 교직원 AI에게 묻기. 원 자료(식단표, 통신문, 규정)를 근거로 답하고 근거 문서를 함께 보여 준다 */
export function AskPage() {
  const ask = useStaffAsk();
  const toast = useToast();
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const last = useRef<HTMLDivElement>(null);
  const q = text.trim();

  const send = (question: string) => {
    if (!question.trim() || ask.isPending) return;
    ask.mutate(question.trim(), {
      onSuccess: (a) => {
        setTurns((t) => [...t, { q: question.trim(), a }]);
        setText("");
        requestAnimationFrame(() => last.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }));
      },
      onError: (e) => {
        if (e instanceof ApiError && e.status === 503) toast({ kind: "error", title: "지금은 답변을 만들 수 없어요", sub: "잠시 뒤에 다시 물어봐 주세요" });
        else if (e instanceof ApiError && e.status === 403) toast({ kind: "error", title: "선생님 계정에서만 쓸 수 있어요" });
        else toast({ kind: "error", title: "답변을 받지 못했어요", sub: "연결을 확인하고 다시 눌러 주세요" });
      },
    });
  };

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop back={{ to: "/teacher/home", label: "홈" }} title="AI에게 묻기" sub="원 자료를 보고 답해요. 중요한 내용은 근거 문서를 열어 확인해 주세요" />

      {turns.length === 0 && !ask.isPending && (
        <section className="mt-5" aria-label="질문 예시">
          <h2 className="mb-2 px-1 text-footnote font-semibold text-ink2">이런 걸 물어볼 수 있어요</h2>
          <ul className="grid gap-2">
            {EXAMPLES.map((e) => (
              <li key={e}>
                <button type="button" onClick={() => setText(e)} className="w-full rounded-lg bg-card p-3 text-left text-callout shadow-card active:scale-[.99]">{e}</button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <div className="mt-5 grid gap-4" aria-live="polite">
        {turns.map((t, i) => (
          <article key={i} className="grid gap-2">
            <p className="ml-auto max-w-[85%] break-keep rounded-lg bg-tint px-3 py-2 text-callout text-accent-ink">{t.q}</p>
            <div className="rounded-lg bg-card p-4 shadow-card">
              <span className="text-caption font-bold text-accent-ink">AI 답변</span>
              <Markdown text={t.a.answer} className="mt-1 text-callout" />
              {t.a.conflict && <p className="mt-3 rounded-md bg-fill px-3 py-2 text-footnote text-ink">자료마다 내용이 달라요. 아래 근거 문서를 확인해 주세요.</p>}
              {t.a.evidence.length > 0 ? (
                <ul className="mt-3 grid gap-1.5 border-t border-sep pt-3" aria-label="근거 문서">
                  {t.a.evidence.map((e) => (
                    <li key={`${e.document_id}-${e.location}`} className="text-footnote">
                      <Link to={`/teacher/class/${e.document_id}`} className="font-semibold text-accent-ink">{e.title}</Link>
                      <span className="text-ink2">{e.location ? `, ${e.location}` : ""}{e.effective_date ? `, ${e.effective_date}부터` : ""}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="mt-3 text-footnote text-ink2">근거로 찾은 문서가 없어요. 자료에서 직접 확인해 주세요.</p>
              )}
            </div>
          </article>
        ))}
        {ask.isPending && (
          <div role="status" className="rounded-lg bg-card p-4 text-callout text-ink2 shadow-card">답변을 찾고 있어요</div>
        )}
        <div ref={last} />
      </div>

      <form
        className="mt-5 grid gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          send(q);
        }}
      >
        <label className="grid gap-1.5">
          <span className="px-1 text-footnote font-semibold text-ink2">질문</span>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value.slice(0, MAX))}
            rows={3}
            placeholder="궁금한 내용을 적어 주세요"
            className="w-full resize-none rounded-md border-[1.5px] border-line bg-card p-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]"
          />
        </label>
        <Button type="submit" loading={ask.isPending} disabled={!q} className="w-full">묻기</Button>
      </form>
    </div>
  );
}
