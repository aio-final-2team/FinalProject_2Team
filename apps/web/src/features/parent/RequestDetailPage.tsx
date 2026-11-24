import { useState } from "react";
import { useParams } from "react-router";
import { TYPE_LABEL, useConfirmRequest, usePostMessage, useRequest } from "@/api/requests";
import { Dock, PrimaryButton } from "@/components/Dock";
import { ScreenTop } from "@/components/ScreenTop";
import { QueryState } from "@/components/QueryState";
import { useToast } from "@/components/Toast";

const STEPS = ["접수", "선생님 확인", "답변", "완료"];
/** 요청 상태 → 진행 단계 (디자인 시스템 7.12 가로 점 단계). escalated면 2단계 이름이 '원장님 확인' */
const STEP_OF: Record<string, number> = { received: 0, classified: 0, needs_info: 1, assigned: 1, awaiting_review: 1, escalated: 1, on_hold: 1, approved: 1, sent_or_booked: 2, completed: 3, rejected: 3 };

/** P-04 요청 상세 (T21 뼈대): 진행 단계, 대화, 답변 출처, 민원 '확인했어요', 이어 쓰기 */
export function RequestDetailPage() {
  const { requestId } = useParams();
  const q = useRequest(requestId);
  const confirm = useConfirmRequest(requestId ?? "");
  const post = usePostMessage(requestId ?? "");
  const toast = useToast();
  const [text, setText] = useState("");
  const d = q.data;
  const r = d?.request;
  const step = r ? STEP_OF[r.status] ?? 1 : 0;
  const closed = r?.status === "completed" || r?.status === "rejected";
  const canConfirm = r?.type === "complaint" && r.status === "sent_or_booked" && !r.parent_confirmed_at;

  return (
    <div className="px-4 pb-48">
      <ScreenTop audience="parent" back={{ to: "/parent/requests", label: "요청" }} title={r?.title ?? "요청"} sub={r ? <>{TYPE_LABEL[r.type] ?? r.type} · <span className="font-bold text-lav">{r.status_label}</span></> : undefined} />
      <QueryState queries={[q]} skeleton={3} errorTitle="이 요청을 불러오지 못했어요">
      {r && (
        <>
          <ol className="mt-4 grid grid-cols-4 gap-1 rounded-lg bg-card p-3 shadow-card" aria-label="진행 단계">
            {STEPS.map((s, i) => (
              <li key={s} className="grid justify-items-center gap-1 text-center">
                <span className={`size-3.5 rounded-full border-2 ${i < step ? "border-accent bg-accent" : i === step ? "border-accent shadow-[0_0_0_3px_var(--tint)]" : "border-fill2"}`} />
                <span className={`text-caption ${i === step ? "font-bold text-ink" : "text-ink2"}`}>{i === 1 && r.status === "escalated" ? "원장님 확인" : s}</span>
              </li>
            ))}
          </ol>

          <ul className="mt-4 grid gap-2">
            {d!.messages.map((m) => (
              <li key={m.id} className={`max-w-[88%] rounded-2xl px-3 py-2.5 text-callout ${(m.sender_role === undefined ? m.sender_type === "user" : m.sender_role === "parent") ? "ml-auto rounded-br-sm bg-brand-fill text-on-brand" : "rounded-bl-sm bg-card shadow-card"}`}>
                {m.body}
              </li>
            ))}
          </ul>

          {d!.sources && d!.sources.length > 0 && (
            <div className="mt-3 rounded-lg bg-ok-tint p-3 text-footnote">
              <b className="text-ok">답변 출처</b>
              {d!.sources.map((s, i) => (
                <p key={i} className="mt-0.5 text-ink">{s.document_title}{s.location ? ` · ${s.location}` : ""}</p>
              ))}
            </div>
          )}
          {d!.rejection && (
            <div className="mt-3 rounded-lg bg-card p-3 text-footnote shadow-card">
              <b>처리할 수 없는 요청이에요</b>
              <p className="mt-0.5 text-ink2">{d!.rejection.reason_text}</p>
            </div>
          )}

          <div className="mb-2 mt-5 px-1 text-footnote font-semibold text-ink2">진행 기록</div>
          <ol className="grid gap-1.5 rounded-lg bg-card p-3 shadow-card">
            {d!.timeline.map((t, i) => (
              <li key={i} className="flex items-center justify-between text-footnote">
                <span className={i === d!.timeline.length - 1 ? "font-semibold" : "text-ink2"}>{t.label}</span>
                <time className="text-ink2 tabular-nums">{new Date(t.at).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false })}</time>
              </li>
            ))}
          </ol>

          {!closed && (
            <label className="mt-5 grid gap-1.5">
              <span className="px-1 text-footnote font-semibold text-ink2">이어서 쓰기</span>
              <div className="flex gap-2">
                <input value={text} onChange={(e) => setText(e.target.value)} maxLength={2000} placeholder="추가로 알려 줄 내용" className="h-12 min-w-0 flex-1 rounded-md border-[1.5px] border-line bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
                <button
                  disabled={!text.trim() || post.isPending}
                  onClick={() => post.mutate(text.trim(), { onSuccess: () => setText(""), onError: () => toast({ kind: "error", title: "답글을 보내지 못했어요", sub: "쓴 내용은 그대로 남아 있어요.\n잠시 뒤 다시 눌러 주세요" }) })}
                  className="h-12 shrink-0 rounded-md bg-tint px-4 text-callout font-semibold text-accent-ink disabled:opacity-50"
                >
                  보내기
                </button>
              </div>
            </label>
          )}

          {canConfirm && (
            <Dock>
              <PrimaryButton loading={confirm.isPending} onClick={() => confirm.mutate(undefined, { onSuccess: () => toast({ kind: "ok", title: "확인했다고 알려 드렸어요" }) })}>
                확인했어요
              </PrimaryButton>
            </Dock>
          )}
        </>
      )}
      </QueryState>
    </div>
  );
}
