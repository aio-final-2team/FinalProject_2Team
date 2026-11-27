import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import { ApiError } from "@/api/client";
import { useStaffAsk, type StaffAnswer } from "@/api/staff";
import { useSession } from "@/app/session";
import { SymbolMark } from "@/components/Brand";
import { Markdown } from "@/components/Markdown";
import { ScreenTop } from "@/components/ScreenTop";
import { useToast } from "@/components/Toast";

type Turn = { q: string; a: StaffAnswer };
const MAX = 2000;
const STORE = (uid?: string) => `yuchion.ask.${uid ?? "-"}`;
const EXAMPLES = ["12월 크리스마스 행사는 언제예요?", "이번 주 급식에 알레르기 식재료가 있나요?"];

/** 이 탭에서 나눈 대화는 화면을 옮겨 다녀도 남긴다. 저장이 막힌 브라우저면 이번 화면에서만 쓴다 */
const load = (uid?: string): Turn[] => {
  try {
    return JSON.parse(sessionStorage.getItem(STORE(uid)) ?? "[]");
  } catch {
    return [];
  }
};
const save = (uid: string | undefined, t: Turn[]) => {
  try {
    sessionStorage.setItem(STORE(uid), JSON.stringify(t));
  } catch {
    /* 저장이 막혀도 이번 화면에서는 동작한다 */
  }
};

/** AI 말풍선 앞의 작은 '온' 심볼 */
const Avatar = () => <SymbolMark className="mt-5 size-8 shrink-0" />;

/**
 * 교직원 AI에게 묻기. 대화 모양으로 보여 주지만 서버가 질문마다 따로 답한다(앞 대화를 기억하지 못한다).
 * 원 자료를 근거로 답하고 근거 문서를 함께 보여 준다.
 */
export function AskPage() {
  const ask = useStaffAsk();
  const { user } = useSession();
  const uid = user?.id;
  const toast = useToast();
  const [text, setText] = useState("");
  const [turns, setTurns] = useState<Turn[]>(() => load(uid));
  const [pending, setPending] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const box = useRef<HTMLTextAreaElement>(null);
  const q = text.trim();

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end", behavior: "smooth" });
  }, [turns.length, pending]);

  /* 입력칸은 글 길이에 맞춰 늘어난다(최대 4줄) */
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 108)}px`;
  }, [text]);

  const send = (question: string) => {
    const t = question.trim();
    if (!t || ask.isPending) return;
    setPending(t);
    setText("");
    ask.mutate(t, {
      onSuccess: (a) =>
        setTurns((p) => {
          const next = [...p, { q: t, a }].slice(-20);
          save(uid, next);
          return next;
        }),
      onError: (e) => {
        setText(t);
        if (e instanceof ApiError && e.status === 503) toast({ kind: "error", title: "지금은 답변을 만들 수 없어요", sub: "잠시 뒤에 다시 물어봐 주세요" });
        else if (e instanceof ApiError && e.status === 403) toast({ kind: "error", title: "선생님 계정에서만 쓸 수 있어요" });
        else toast({ kind: "error", title: "답변을 받지 못했어요", sub: "연결을 확인하고 다시 눌러 주세요" });
      },
      onSettled: () => setPending(null),
    });
  };

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-52 lg:pb-6">
      <ScreenTop
        back={{ to: "/teacher/home", label: "홈" }}
        title="AI에게 묻기"
        sub="원 자료를 보고 답해요"
        right={
          turns.length ? (
            <button
              type="button"
              onClick={() => {
                setTurns([]);
                save(uid, []);
              }}
              className="inline-flex h-9 items-center rounded-md px-2.5 text-footnote font-semibold text-ink2 active:scale-[.97]"
            >
              대화 지우기
            </button>
          ) : undefined
        }
      />

      <div className="mt-4 grid gap-4" aria-live="polite">
        <div className="flex items-start gap-2">
          <Avatar />
          <div className="min-w-0">
            <span className="text-caption font-semibold text-ink2">유치온 AI</span>
            <p className="mt-1 rounded-2xl rounded-tl-md bg-card px-3.5 py-2.5 text-callout shadow-card">궁금한 내용을 적어 주세요. 식단표, 가정통신문, 규정 같은 원 자료를 보고 답해요.</p>
          </div>
        </div>

        {turns.map((t, i) => (
          <div key={i} className="grid gap-4">
            <p className="ml-auto max-w-[82%] break-keep rounded-2xl rounded-br-md bg-brand-fill px-3.5 py-2.5 text-callout text-on-brand">{t.q}</p>
            <div className="flex items-start gap-2">
              <Avatar />
              <div className="min-w-0 max-w-[88%]">
                <span className="text-caption font-semibold text-ink2">유치온 AI</span>
                <div className="mt-1 rounded-2xl rounded-tl-md bg-card px-3.5 py-2.5 shadow-card">
                  <Markdown text={t.a.answer} className="text-callout" />
                  {t.a.conflict && <p className="mt-2 rounded-md bg-fill px-2.5 py-1.5 text-footnote text-ink">자료마다 내용이 달라요. 근거 문서를 확인해 주세요.</p>}
                </div>
                {t.a.evidence.length > 0 ? (
                  <ul className="mt-1.5 flex flex-wrap gap-1.5" aria-label="근거 문서">
                    {t.a.evidence.map((e) => (
                      <li key={`${e.document_id}-${e.location}`}>
                        <Link to={`/teacher/class/${e.document_id}`} className="inline-flex min-h-8 items-center rounded-full bg-tint px-3 text-caption font-semibold text-accent-ink active:scale-[.97]">
                          {e.title}
                          {e.location && e.location !== "본문" ? `, ${e.location}` : ""}
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1.5 px-1 text-caption text-ink2">근거로 찾은 문서가 없어요. 자료에서 직접 확인해 주세요.</p>
                )}
              </div>
            </div>
          </div>
        ))}

        {pending && (
          <div className="grid gap-4">
            <p className="ml-auto max-w-[82%] break-keep rounded-2xl rounded-br-md bg-brand-fill px-3.5 py-2.5 text-callout text-on-brand">{pending}</p>
            <div className="flex items-start gap-2" role="status" aria-label="답변을 찾고 있어요">
              <SymbolMark motion="scan" className="mt-1 size-8 shrink-0" />
              <p className="flex h-10 items-center gap-1.5 rounded-2xl rounded-tl-md bg-card px-4 shadow-card" aria-hidden>
                {[0, 1, 2].map((d) => (
                  <span key={d} className="m-dot size-1.5 rounded-full bg-ink2" style={{ animationDelay: `${d * 0.15}s` }} />
                ))}
              </p>
            </div>
          </div>
        )}
        <div ref={end} />
      </div>

      {/* 입력 칸: 휴대폰에서는 아래 탭 바 바로 위에 붙는다. 캐릭터가 솟는 높이(--tab-lift)만큼 아래 여백을 둔다 */}
      <div data-bottom-bar className="glass fixed inset-x-0 bottom-[calc(64px+env(safe-area-inset-bottom))] z-20 border-t border-sep bg-bar px-4 pb-[calc(10px+var(--tab-lift,0px))] pt-2.5 backdrop-blur-xl lg:sticky lg:bottom-0 lg:mt-6">
        <div className="mx-auto grid max-w-[680px] gap-2">
          {turns.length === 0 && !pending && (
            <div className="flex flex-wrap gap-2" role="group" aria-label="질문 예시">
              {EXAMPLES.map((e) => (
                <button key={e} type="button" onClick={() => send(e)} className="h-9 rounded-full border border-sep bg-card px-3 text-footnote font-semibold text-ink active:scale-[.97]">
                  {e}
                </button>
              ))}
            </div>
          )}
          <form
            className="flex items-end gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              send(q);
            }}
          >
            <textarea
              ref={box}
              value={text}
              rows={1}
              maxLength={MAX}
              aria-label="질문"
              placeholder="궁금한 내용을 적어 주세요"
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  send(q);
                }
              }}
              className="max-h-[108px] min-h-11 min-w-0 flex-1 resize-none rounded-[22px] border-[1.5px] border-line bg-card px-4 py-2.5 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]"
            />
            <button
              type="submit"
              disabled={!q || ask.isPending}
              className="h-11 shrink-0 rounded-full bg-brand-fill px-4 text-callout font-semibold text-on-brand transition-[transform,filter] duration-100 active:scale-[.97] disabled:bg-fill2 disabled:text-ink2"
            >
              묻기
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
