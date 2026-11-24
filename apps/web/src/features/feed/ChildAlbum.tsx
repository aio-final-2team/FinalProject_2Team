import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAlbum, usePosts, type Lane, type Photo, type Post } from "@/api/feed";
import { useSession } from "@/app/session";
import { AuthPhoto } from "@/components/AuthPhoto";
import { Icon } from "@/components/Icon";
import { ScreenTop } from "@/components/ScreenTop";
import { QueryState } from "@/components/QueryState";
import { StateView } from "@/components/StateView";
import { useToast } from "@/components/Toast";
import { nameI } from "@/domain/notes";
import { PhotoViewer } from "./parts";
import { ScopeSheet } from "./ScopeSheet";

type Me = { children: { id: string; display_name: string; classroom_id: string }[] };
type Group = { post: Post; photos: Photo[] };

const DAY = 24 * 60 * 60 * 1000;
const dayLabel = (iso: string) => (new Date(iso).toDateString() === new Date().toDateString() ? "오늘" : new Date(iso).toLocaleDateString("ko-KR", { month: "long", day: "numeric" }));
const title = (body: string) => body.split("\n")[0].slice(0, 22);

/**
 * 우리 애 (학부모 앨범). 반 소식 글 중에서 내 아이가 표시된 사진만 행사(글)별로 모아 보여 준다.
 * 아이 표시는 올린 사람이 직접 한다. 사진 AI가 붙기 전이라 '이 아이가 맞나요?'와 성장 앨범은 준비 중 칸으로만 둔다.
 */
export function ChildAlbum() {
  const { user } = useSession();
  const toast = useToast();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/v1/me") });
  const kids = me.data?.children ?? [];
  const [pick, setPick] = useState<string>();
  const kid = kids.find((k) => k.id === pick) ?? kids[0];
  const lane: Lane | undefined = kid ? { kind: "class", id: kid.classroom_id } : undefined;
  const album = useAlbum(lane, kid?.id);
  const posts = usePosts(lane);
  const [scope, setScope] = useState(false);
  const [viewer, setViewer] = useState<{ photos: Photo[]; index: number } | null>(null);

  const { groups, week, people } = useMemo(() => {
    const ids = new Set((album.data ?? []).map((p) => p.id));
    const groups: Group[] = (posts.data ?? [])
      .map((post) => ({ post, photos: post.photos.filter((p) => ids.has(p.id)) }))
      .filter((g) => g.photos.length > 0)
      .sort((a, b) => +new Date(b.post.created_at) - +new Date(a.post.created_at));
    const week = groups.filter((g) => Date.now() - +new Date(g.post.created_at) < 7 * DAY).reduce((n, g) => n + g.photos.length, 0);
    return { groups, week, people: new Set(groups.map((g) => g.post.author_id)).size };
  }, [album.data, posts.data]);

  const total = album.data?.length ?? 0;
  const name = kid?.display_name ?? "아이";
  const soon = (what: string) => toast({ kind: "ok", title: `${what} 준비 중이에요`, sub: "사진 AI가 연결되면 열려요" });

  return (
    <div className="pb-24">
      <div className="px-4">
        <ScreenTop audience="parent" title="우리 애" sub={`반 사진에서 모은 ${name} 기록`} right={<>
          <button type="button" aria-label="공유" onClick={() => soon("공유는")} className="grid size-11 place-items-center rounded-full text-ink active:scale-95">
            <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M12 15V4M8 8l4-4 4 4M5 12v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" /></svg>
          </button>
          <button type="button" aria-label={`${name} 사진 공개 범위 설정`} onClick={() => setScope(true)} className="grid size-11 place-items-center rounded-full text-ink active:scale-95">
            <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>
          </button>
        </>} />
      </div>

      <QueryState queries={[me, album, posts]} skeleton={3} errorTitle="앨범을 불러오지 못했어요">
        <div className="px-4">
          {kids.length > 1 && (
            <div className="mt-3 flex flex-wrap gap-2" role="group" aria-label="아이 고르기">
              {kids.map((k) => (
                <button key={k.id} type="button" aria-pressed={kid?.id === k.id} onClick={() => setPick(k.id)} className={`h-9 rounded-full border px-3 text-footnote font-semibold ${kid?.id === k.id ? "border-accent bg-tint text-accent-ink" : "border-sep bg-card"}`}>{k.display_name}</button>
              ))}
            </div>
          )}

          <div className="mt-4 flex items-center gap-4">
            <span aria-hidden className="grid size-[72px] shrink-0 place-items-center rounded-full bg-tint text-[28px] font-bold text-accent-ink">{name.slice(-1)}</span>
            <div className="min-w-0">
              <h2 className="truncate text-title font-bold tracking-[-0.02em]">{name}</h2>
              <p className="text-footnote text-ink2">우리 반</p>
            </div>
          </div>

          <dl className="mt-4 grid grid-cols-3 rounded-lg bg-card py-3 text-center shadow-card [&>div+div]:border-l [&>div+div]:border-sep">
            {[
              [week, "이번 주 사진"],
              [people, "올려 준 사람"],
              [total, "모인 사진"],
            ].map(([n, label]) => (
              <div key={label as string}>
                <dd className="text-title font-bold tabular-nums">{n}</dd>
                <dt className="text-caption text-ink2">{label}</dt>
              </div>
            ))}
          </dl>

          <section aria-label="사진 AI 확인" className="mt-4 rounded-lg border-[1.5px] border-dashed border-line bg-card p-3">
            <p className="flex items-center gap-2 text-callout font-semibold"><Icon name="ai" className="size-5 text-accent" />이 아이, {nameI(name)} 맞나요?<span className="ml-auto rounded-full bg-fill px-2 py-0.5 text-caption font-semibold text-ink2">준비 중</span></p>
            <p className="mt-1 text-footnote text-ink2">사진 AI가 연결되면 확실하지 않은 사진을 여기서 물어봐요.</p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button type="button" disabled className="h-10 rounded-md bg-fill text-footnote font-semibold text-ink2 opacity-60">맞아요</button>
              <button type="button" disabled className="h-10 rounded-md bg-fill text-footnote font-semibold text-ink2 opacity-60">아니에요</button>
            </div>
          </section>

          {groups.length === 0 ? (
            <StateView kind="empty" audience="parent" title={`아직 ${nameI(name)}가 나온 사진이 없어요`} sub={"소식에 글을 올릴 때 사진에 나온 아이를 고르면\n여기에 모여요"} />
          ) : (
            <div className="mt-6 grid gap-6">
              {groups.map((g) => {
                const mine = g.post.author_id === user?.id;
                return (
                  <section key={g.post.id} aria-label={title(g.post.body)}>
                    <h3 className="flex items-baseline gap-2 text-headline font-bold">
                      <span className="min-w-0 truncate">{title(g.post.body)}</span>
                      <time className="shrink-0 text-footnote font-medium text-ink2">{dayLabel(g.post.created_at)}</time>
                    </h3>
                    <p className="mt-0.5 text-footnote text-ink2">{mine ? "내가" : "다른 보호자가"} 올린 사진 {g.photos.length}장</p>
                    <ul className="mt-2 grid grid-cols-3 gap-1 overflow-hidden rounded-lg">
                      {g.photos.map((p, i) => (
                        <li key={p.id} className="relative">
                          <button type="button" aria-label={`${title(g.post.body)} 사진 ${i + 1}장 크게 보기`} onClick={() => setViewer({ photos: g.photos, index: i })} className="block w-full active:opacity-80">
                            <AuthPhoto photo={p} className="aspect-square w-full" />
                          </button>
                          <span className="pointer-events-none absolute bottom-1 left-1 rounded bg-ink/60 px-1.5 py-0.5 text-caption font-semibold text-card">{mine ? "내가 올림" : "보호자"}</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                );
              })}
            </div>
          )}

          <section aria-label="성장 앨범" className="mt-8 rounded-lg bg-tint p-4">
            <p className="flex items-center gap-2 text-callout font-bold">{nameI(name)}의 1년<span className="rounded-full bg-card px-2 py-0.5 text-caption font-semibold text-ink2">준비 중</span></p>
            <p className="mt-1 text-footnote text-ink2">성장 영상과 앨범은 준비 중이에요.</p>
          </section>
        </div>
      </QueryState>

      <ScopeSheet open={scope} onClose={() => setScope(false)} kid={kid} />
      {viewer && <PhotoViewer photos={viewer.photos} index={viewer.index} onIndex={(i) => setViewer({ ...viewer, index: i })} onClose={() => setViewer(null)} />}
    </div>
  );
}
