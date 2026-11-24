import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { Buddy } from "@/components/Brand";
import { QueryState } from "@/components/QueryState";
import { Dock, SubButton } from "@/components/Dock";
import { Icon } from "@/components/Icon";
import { useToast } from "@/components/Toast";
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
  const toast = useToast();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/v1/me") });
  const notes = useQuery({
    queryKey: ["parent-notes", date],
    queryFn: () => api<{ items: DailyNote[] }>(`/api/v1/daily-notes?date=${date}&size=20`).then((r) => r.items),
  });
  const child = me.data?.children[0];
  const note = notes.data?.find((n) => n.child_id === child?.id) ?? notes.data?.[0];
  const sentAt = note?.sent_at ? new Date(note.sent_at).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", hour12: false }) : "";
  const childLine = note?.content.items.find((i) => i.key === "child")?.value;
  const facts = note?.content.items.filter((i) => i.key === "meal" || i.key === "supplies" || i.key === "medication" || i.key === "pickup") ?? [];
  const rest = note?.content.items.filter((i) => i.key === "day") ?? [];

  return (
    <div className="min-h-full pb-48">
      {/* 블루 머리: 학부모 홈에만 브랜드 블루를 넓게 쓴다 */}
      <header className="bg-brand-fill px-4 pb-6 pt-[max(12px,env(safe-area-inset-top))] text-on-brand">
        <div className="mx-auto flex max-w-[680px] items-center justify-between">
          <img src={wordWhite} alt="유치온" className="h-5 w-auto" />
          <Link to="/parent/notifications" className="grid size-11 place-items-center rounded-md" aria-label="알림">
            <Icon name="bell" className="size-6" />
          </Link>
        </div>
        <div className="mx-auto max-w-[680px]">
          <h1 className="mt-4 text-large-title font-bold tracking-[-0.025em]">{child ? `${nameI(child.display_name)}의 오늘` : "오늘"}</h1>
          <p className="mt-0.5 text-footnote font-medium text-on-brand/80">{dateLabel(date)}</p>
        </div>
      </header>

      <div className="mx-auto max-w-[680px] px-4 pt-4">
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
                <time className="tabular-nums">{sentAt}</time>
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

      {note && (
        <Dock>
          <SubButton tone="gray" className="h-[52px] w-full" onClick={() => toast({ kind: "ok", title: "답장은 다음 단계에서 열려요", sub: "답장 API가 아직 없어요" })}>
            선생님께 답장하기
          </SubButton>
        </Dock>
      )}
    </div>
  );
}
