import { useState } from "react";
import { useParams } from "react-router";
import { TYPE_LABEL, useCancelRequest, useConfirmRequest, usePatchCare, usePostMessage, useRequest, type CareInput } from "@/api/requests";
import { ApiError } from "@/api/client";
import { Button } from "@/components/Button";
import { ConsultSlots } from "./ConsultSlots";
import { Sheet } from "@/components/Sheet";
import { Dock, PrimaryButton } from "@/components/Dock";
import { ScreenTop } from "@/components/ScreenTop";
import { QueryState } from "@/components/QueryState";
import { fmtDateTime } from "@/domain/datetime";
import { useToast } from "@/components/Toast";
import { term } from "@/domain/wording";

const STEPS = ["접수", "선생님 확인", "답변", "완료"];
/** 유형별 3번째 단계 이름: 상담은 예약, 투약·귀가는 처리, 문의·민원은 답변 */
const THIRD: Record<string, string> = { consultation: "예약", medication: "처리", pickup: "처리" };
/** 요청 상태 → 진행 단계 (디자인 시스템 7.12 가로 점 단계). escalated면 2단계 이름이 '원장님 확인' */
const STEP_OF: Record<string, number> = { received: 0, classified: 0, needs_info: 1, assigned: 1, awaiting_review: 1, escalated: 1, on_hold: 1, approved: 1, sent_or_booked: 2, completed: 3, rejected: 3 };

/** P-04 요청 상세: 대화·추가 요청을 먼저 보여 주고 진행 기록은 맨 아래에 둔다. */
export function RequestDetailPage() {
  const { requestId } = useParams();
  const q = useRequest(requestId, true);
  const confirm = useConfirmRequest(requestId ?? "");
  const post = usePostMessage(requestId ?? "");
  const toast = useToast();
  const [text, setText] = useState("");
  const cancel = useCancelRequest(requestId ?? "");
  const patch = usePatchCare(requestId ?? "");
  const [sheet, setSheet] = useState<null | "cancel" | "edit">(null);
  const [edit, setEdit] = useState<CareInput>({});
  const d = q.data;
  const r = d?.request;
  const step = r ? STEP_OF[r.status] ?? 1 : 0;
  const closed = r?.status === "completed" || r?.status === "rejected";
  const isCare = r?.type === "medication" || r?.type === "pickup";
  const careEditable = isCare && !closed;
  const canConfirm = r?.type === "complaint" && r.status === "sent_or_booked" && !r.parent_confirmed_at;

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-48">
      <ScreenTop audience="parent" back={{ to: "/parent/requests", label: "요청" }} title={r?.title ?? "요청"} sub={r ? <>{TYPE_LABEL[r.type] ?? r.type} · <span className="font-bold text-lav">{term(r.status_label)}</span></> : undefined} />
      <QueryState queries={[q]} skeleton={3} errorTitle="이 요청을 불러오지 못했어요">
      {r && (
        <>
          <ol className="mt-4 grid grid-cols-4 gap-1 rounded-lg bg-card p-3 shadow-card" aria-label="진행 단계">
            {STEPS.map((name, i) => { const s = i === 2 ? (THIRD[r.type] ?? name) : name; return (
              <li key={s} className="grid justify-items-center gap-1 text-center">
                <span className={`size-3.5 rounded-full border-2 ${i < step ? "border-accent bg-accent" : i === step ? "border-accent shadow-[0_0_0_3px_var(--tint)]" : "border-fill2"}`} />
                <span className={`text-caption ${i === step ? "font-bold text-ink" : "text-ink2"}`}>{i === 1 && r.status === "escalated" ? "원장님 확인" : s}</span>
              </li>
            ); })}
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

          {isCare && d!.care && (
            <section className="mt-3 rounded-lg bg-card p-3 text-footnote shadow-card" aria-label="투약·귀가 내용">
              <b className="block text-callout">{r!.type === "medication" ? "투약 내용" : "귀가 내용"}</b>
              <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                {(r!.type === "medication"
                  ? [["약 이름", d!.care.medication_name], ["먹일 양", d!.care.medication_dose], ["먹일 시간", d!.care.medication_time]]
                  : [["데리러 오는 분", d!.care.pickup_name], ["관계", d!.care.pickup_relation]]
                ).map(([k, v]) => (
                  <div key={k} className="contents">
                    <dt className="text-ink2">{k}</dt>
                    <dd className={v ? "font-semibold" : "text-danger"}>{v || "아직 적지 않았어요"}</dd>
                  </div>
                ))}
              </dl>
              {careEditable && (
                <div className="mt-3 grid grid-cols-2 gap-2">
                  <button type="button" onClick={() => { setEdit({ medication_name: d!.care!.medication_name ?? "", medication_dose: d!.care!.medication_dose ?? "", medication_time: d!.care!.medication_time ?? "", pickup_name: d!.care!.pickup_name ?? "", pickup_relation: d!.care!.pickup_relation ?? "" }); setSheet("edit"); }} className="h-10 rounded-md bg-tint font-semibold text-accent-ink active:scale-[.97]">내용 고치기</button>
                  <button type="button" onClick={() => setSheet("cancel")} className="h-10 rounded-md bg-fill font-semibold text-ink active:scale-[.97]">요청 취소</button>
                </div>
              )}
            </section>
          )}

          {r!.type === "consultation" && d!.consultation && <ConsultSlots requestId={requestId ?? ""} status={r!.status} consultation={d!.consultation} />}

          {!closed && (
            <label className="mt-5 grid gap-1.5">
              <span className="px-1 text-callout font-bold text-ink">{r.type === "consultation" ? "상담 요청 내용" : "추가로 전할 내용"}</span>
              <div className="flex items-end gap-2">
                <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} maxLength={2000} placeholder={r.type === "consultation" ? "선생님과 상담하고 싶은 내용을 적어 주세요" : "선생님에게 추가로 알려 줄 내용을 적어 주세요"} className="min-h-24 min-w-0 flex-1 resize-none rounded-xl border-[1.5px] border-line bg-card px-3 py-2.5 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
                <button
                  disabled={!text.trim() || post.isPending}
                  onClick={() => post.mutate(text.trim(), { onSuccess: () => setText(""), onError: () => toast({ kind: "error", title: "답글을 보내지 못했어요", sub: "쓴 내용은 그대로 남아 있어요.\n잠시 뒤 다시 눌러 주세요" }) })}
                  className="h-12 shrink-0 rounded-lg bg-tint px-4 text-callout font-semibold text-accent-ink transition-transform duration-100 active:scale-[.97] disabled:opacity-50"
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

          <div className="mb-2 mt-7 px-1 text-footnote font-semibold text-ink2">진행 기록</div>
          <ol className="grid gap-1.5 rounded-xl bg-card p-3 shadow-card">
            {d!.timeline.map((t, i) => (
              <li key={i} className="flex items-center justify-between text-footnote">
                <span className={i === d!.timeline.length - 1 ? "font-semibold" : "text-ink2"}>{t.label}</span>
                <time className="text-ink2 tabular-nums">{fmtDateTime(t.at)}</time>
              </li>
            ))}
          </ol>
        </>
      )}
      </QueryState>
      <Sheet open={sheet === "cancel"} onClose={() => setSheet(null)} title="이 요청을 취소할까요?">
        <p className="text-footnote text-ink2">선생님에게 취소했다고 알려요. 이미 끝났거나 처리할 수 없게 된 요청은 취소할 수 없어요.</p>
        <Button
          variant="danger"
          loading={cancel.isPending}
          onClick={() => cancel.mutate(undefined, { onSuccess: () => { setSheet(null); toast({ kind: "ok", title: "요청을 취소했어요" }); }, onError: (e) => { setSheet(null); toast({ kind: "error", title: e instanceof ApiError && e.status === 409 ? "이미 처리된 요청이라 취소할 수 없어요" : "취소하지 못했어요", sub: e instanceof ApiError && e.status === 409 ? undefined : "연결을 확인하고 다시 눌러 주세요" }); } })}
        >
          요청 취소
        </Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>닫기</Button>
      </Sheet>
      <Sheet open={sheet === "edit"} onClose={() => setSheet(null)} title="내용 고치기">
        <p className="text-footnote text-ink2">고치면 선생님이 다시 확인해요.</p>
        {(r?.type === "medication"
          ? ([["medication_name", "약 이름"], ["medication_dose", "먹일 양"], ["medication_time", "먹일 시간"]] as const)
          : ([["pickup_name", "데리러 오는 분 이름"], ["pickup_relation", "아이와의 관계"]] as const)
        ).map(([k, label]) => (
          <label key={k} className="grid gap-1.5">
            <span className="text-footnote font-semibold">{label}</span>
            <input value={edit[k] ?? ""} onChange={(e) => setEdit((x) => ({ ...x, [k]: e.target.value }))} maxLength={100} className="h-12 rounded-md border-[1.5px] border-line bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
          </label>
        ))}
        <Button
          loading={patch.isPending}
          onClick={() => {
            const keys = r?.type === "medication" ? (["medication_name", "medication_dose", "medication_time"] as const) : (["pickup_name", "pickup_relation"] as const);
            patch.mutate({ version: d!.care!.version, ...Object.fromEntries(keys.map((k) => [k, (edit[k] ?? "").trim() || null])) }, {
              onSuccess: () => { setSheet(null); toast({ kind: "ok", title: "내용을 고쳤어요", sub: "선생님이 다시 확인해요" }); },
              onError: (e) => { setSheet(null); toast({ kind: "error", title: e instanceof ApiError && e.status === 409 ? "방금 선생님이 상태를 바꿨어요" : "고치지 못했어요", sub: "최신 내용으로 다시 불러왔어요.\n확인하고 다시 눌러 주세요" }); },
            });
          }}
        >
          고치기
        </Button>
        <Button variant="plain" size="sm" onClick={() => setSheet(null)}>닫기</Button>
      </Sheet>
    </div>
  );
}
