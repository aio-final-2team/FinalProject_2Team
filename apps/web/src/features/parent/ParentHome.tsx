import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { TYPE_LABEL, useMyRequests } from "@/api/requests";
import { Buddy } from "@/components/Brand";
import { QueryState } from "@/components/QueryState";
import { Icon } from "@/components/Icon";
import wordWhite from "@/assets/brand/wordmark-white.svg";
import { dateLabel, nameI, todayKST, type DailyNote } from "@/domain/notes";

type Me = { user: { display_name: string }; children: { id: string; display_name: string; classroom_id: string }[] };

/**
 * A-08 학부모 홈 · 오늘 알림장 (디자인 시스템 7.8 블루 머리 · 7.11 알림장 카드).
 * 보호자는 내 아이의 '보낸' 알림장만 받는다 (API 24, open_checks는 늘 빈 목록).
 * [API 없음] 선생님께 답장하기·알림은 아직 API가 없어 모양만 둔다.
 */
export function ParentHome() {
  const date = todayKST();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/v1/me") });
  const notes = useQuery({
    queryKey: ["parent-notes", date],
    queryFn: () => api<{ items: DailyNote[] }>(`/api/v1/daily-notes?date=${date}&size=20`).then((r) => r.items),
  });
  const reqs = useMyRequests();
  /* 내가 답해야 멈춘 요청만 홈에 올린다 (상담 시간 고르기, 빠진 내용 채우기) */
  const todo = (reqs.data?.items ?? []).filter((r) => r.status === "needs_info");
  const child = me.data?.children[0];
  const note = notes.data?.find((n) => n.child_id === child?.id) ?? notes.data?.[0];
  const sentAt = note?.sent_at ? new Date(note.sent_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false }) : "";
  const childLine = note?.content.items.find((i) => i.key === "child")?.value;
  const facts = note?.content.items.filter((i) => i.key === "meal" || i.key === "supplies" || i.key === "medication" || i.key === "pickup") ?? [];
  const rest = note?.content.items.filter((i) => i.key === "day") ?? [];

  return (
    <div className="min-h-full pb-8">
      {/* 블루 머리: 학부모 홈에만 브랜드 블루를 넓게 쓴다 */}
      <header className="bg-brand-fill px-4 pb-6 pt-[max(12px,env(safe-area-inset-top))] text-on-brand">
        <div className="mx-auto flex max-w-[680px] items-center justify-between">
          <img src={wordWhite} alt="유치온" className="h-5 w-auto" />
          <div className="flex items-center">
            <Link to="/parent/notifications" className="grid size-11 place-items-center rounded-md" aria-label="알림">
              <Icon name="bell" className="size-6" />
            </Link>
          </div>
        </div>
        <div className="mx-auto max-w-[680px]">
          <h1 className="mt-4 text-large-title font-bold tracking-[-0.025em]">{child ? `${nameI(child.display_name)}의 오늘` : "오늘"}</h1>
          <p className="mt-0.5 text-footnote font-medium text-on-brand/80">{dateLabel(date)}</p>
        </div>
      </header>

      <div className="mx-auto max-w-[680px] px-4 pt-4">
        {todo.length > 0 && (
          <section aria-label="확인할 일" className="mb-4 overflow-hidden rounded-lg bg-card shadow-card">
            <h2 className="px-3 pt-3 text-footnote font-semibold text-ink2">확인할 일 {todo.length}건</h2>
            <ul>
              {todo.slice(0, 3).map((r) => (
                <li key={r.id} className="[&+&]:border-t [&+&]:border-sep">
                  <Link to={`/parent/requests/${r.id}`} className="flex min-h-14 items-center gap-3 px-3 py-2.5">
                    <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-sm bg-fill text-caption font-bold">{(TYPE_LABEL[r.type] ?? r.type).slice(0, 2)}</span>
                    <span className="min-w-0 flex-1">
                      <b className="block truncate text-headline font-semibold">{r.title ?? "제목 없음"}</b>
                      <span className="text-footnote font-bold text-lav">{r.status_label}</span>
                    </span>
                    <Icon name="chevR" className="size-4 text-ink2" />
                  </Link>
                </li>
              ))}
            </ul>
          </section>
        )}
        <QueryState queries={[me, notes]} skeleton={3} errorTitle="오늘 알림장을 불러오지 못했어요">
        {!note ? (
          <div className="grid justify-items-center gap-2 py-12 text-center">
            <Buddy face="waiting" className="size-20" />
            <b className="text-headline">아직 오늘 알림장이 오지 않았어요</b>
            <p className="text-callout text-ink2">선생님이 보내면 여기에 바로 보여요.</p>
          </div>
        ) : (
          <article className="overflow-hidden rounded-lg bg-card shadow-card">
            {/* 사진 칸은 B안(사진 확장)에서 붙는다. 사진 없는 날 규칙대로 글만 보여 준다 */}
            <div className="p-4">
              <div className="flex justify-between text-caption text-ink2">
                <span>담임 선생님</span>
                <span className="flex items-center gap-2">
                  {note.corrected_at && <b className="text-lav">정정 {new Date(note.corrected_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false })}</b>}
                  <time className="tabular-nums">{sentAt}</time>
                </span>
              </div>
              <h2 className="mt-1.5 text-headline font-bold">{childLine ?? rest[0]?.value ?? "오늘 알림장"}</h2>
              {rest
                .filter((i, k) => (childLine ? i.value !== childLine : k > 0))
                .map((i, k) => (
                  <p key={k} className="mt-1 text-callout">
                    {i.source.type === "request" && <span className="mr-1.5 text-footnote font-semibold text-lav">보호자 요청</span>}
                    {i.value}
                  </p>
                ))}
              {facts.length > 0 && (
                <dl className="mt-3 grid gap-1 border-t border-sep pt-3 text-callout">
                  {facts.map((f, k) => (
                    <div key={k} className="flex gap-2">
                      <dt className="w-14 shrink-0 text-footnote font-semibold text-ink2">{f.label}</dt>
                      <dd className="min-w-0">{f.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
          </article>
        )}
        </QueryState>
      </div>

    </div>
  );
}
