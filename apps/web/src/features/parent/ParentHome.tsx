import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { TYPE_LABEL, useMyRequests } from "@/api/requests";
import { Buddy, MainLogo } from "@/components/Brand";
import { QueryState } from "@/components/QueryState";
import { Icon } from "@/components/Icon";
import { ChildAvatar, type ProfilePhoto } from "@/components/ChildAvatar";
import { dateLabel, itemLabel, nameI, todayKST, type DailyNote } from "@/domain/notes";
import { NoteReply } from "./NoteReply";
import { term } from "@/domain/wording";

type Me = { user: { display_name: string }; children: { id: string; display_name: string; classroom_id: string; profile_photo?: ProfilePhoto }[] };

/**
 * A-08 학부모 홈 · 오늘 알림장 (디자인 시스템 7.8 블루 머리 · 7.11 알림장 카드).
 * 보호자는 내 아이의 '보낸' 알림장만 받는다 (API 24, open_checks는 늘 빈 목록).
 * 답장·준비물 확인은 문서 3.34(API 62·68). 알림은 아직 API가 없다.
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
  const story = rest.filter((i, k) => (childLine ? i.value !== childLine : k > 0));

  return (
    <div className="min-h-full pb-8">
      {/* 블루 머리: 학부모 홈에만 브랜드 블루를 넓게 쓴다 */}
      <header className="relative overflow-hidden bg-brand-fill px-4 pb-6 pt-[max(12px,env(safe-area-inset-top))] text-on-brand">
        <div className="mx-auto flex max-w-[680px] items-center justify-between">
          <MainLogo onBlue className="h-9" />
          <div className="flex items-center">
            <Link to="/parent/notifications" className="grid size-11 place-items-center rounded-md" aria-label="알림">
              <Icon name="bell" className="size-6" />
            </Link>
          </div>
        </div>
        <div className="relative mx-auto max-w-[680px] pr-24 lg:pr-32">
          <h1 className="mt-4 text-large-title font-bold tracking-[-0.01em]">{child ? `${nameI(child.display_name)}의 오늘` : "오늘"}</h1>
          <p className="mt-0.5 text-footnote font-medium text-on-brand/80">{dateLabel(date)}</p>
          <p className="mt-2 text-callout font-medium text-on-brand/90">오늘도 아이의 하루를 함께 볼까요?</p>
          <Buddy face="basic" className="absolute -bottom-5 right-0 size-24 lg:-bottom-6 lg:size-28" />
        </div>
      </header>

      <div className="mx-auto max-w-[680px] px-4 pt-4">
        {todo.length > 0 && (
          <section aria-label="함께 확인해요" className="mb-4 overflow-hidden rounded-xl bg-card shadow-card">
            <h2 className="px-4 pt-4 text-callout font-bold text-ink">함께 확인해요 <span className="ml-1 text-footnote text-accent-ink">{todo.length}건</span></h2>
            <ul>
              {todo.slice(0, 3).map((r) => (
                <li key={r.id} className="[&+&]:border-t [&+&]:border-sep">
                  <Link to={`/parent/requests/${r.id}`} className="flex min-h-14 items-center gap-3 px-4 py-3 transition-colors active:bg-fill">
                    <span aria-hidden className="grid size-9 shrink-0 place-items-center rounded-lg bg-tint font-display text-caption font-bold text-accent-ink">{(TYPE_LABEL[r.type] ?? r.type).slice(0, 2)}</span>
                    <span className="min-w-0 flex-1">
                      <b className="block truncate text-headline font-semibold">{r.title ?? "제목 없음"}</b>
                      <span className="text-footnote font-bold text-lav">{term(r.status_label)}</span>
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
          <article className="overflow-hidden rounded-[24px] bg-card shadow-card">
            {/* 사진 칸은 B안(사진 확장)에서 붙는다. 사진 없는 날 규칙대로 글만 보여 준다 */}
            <div className="p-5">
              <div className="flex items-start gap-3">
                <ChildAvatar name={child?.display_name ?? "아이"} photo={child?.profile_photo} childId={child?.id} size={48} tone="tint" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center justify-between gap-2 text-caption text-ink2">
                    <span className="font-bold text-accent-ink">오늘 알림장</span>
                    <span className="flex items-center gap-2">
                      {note.corrected_at && <b className="text-lav">정정 {new Date(note.corrected_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false })}</b>}
                      <time className="tabular-nums">{sentAt}</time>
                    </span>
                  </div>
                  <h2 className="mt-1.5 text-headline font-bold leading-snug">{childLine ?? rest[0]?.value ?? "아이의 하루가 도착했어요"}</h2>
                </div>
              </div>
              {story.length > 0 && <div className="mt-4 rounded-xl bg-g p-3.5">
                <p className="mb-1 text-footnote font-semibold text-ink2">오늘의 이야기</p>
                {story.map((i, k) => (
                    <p key={k} className="mt-1 text-callout leading-relaxed">
                      {i.source.type === "request" && <span className="mr-1.5 font-display text-footnote font-semibold text-lav">내 요청</span>}
                      {i.value}
                    </p>
                  ))}
              </div>}
              {facts.length > 0 && (
                <dl className="mt-3 grid gap-2 text-callout sm:grid-cols-2">
                  {facts.map((f, k) => (
                    <div key={k} className="rounded-xl bg-tint px-3.5 py-3">
                      <dt className="font-display text-footnote font-bold text-accent-ink">{itemLabel(f)}</dt>
                      <dd className="mt-0.5 min-w-0 leading-relaxed">{f.source.type === "request" && <span className="mr-1.5 font-display text-footnote font-semibold text-lav">내 요청</span>}{f.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
            </div>
            <NoteReply note={note} />
          </article>
        )}
        </QueryState>
      </div>

    </div>
  );
}
