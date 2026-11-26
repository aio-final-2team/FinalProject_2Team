import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router";
import { api } from "@/api/client";
import { useChildren } from "@/api/notes";
import { useAlbum, useDeletePost, useHidePost, usePosts, type Lane, type Photo, type Post } from "@/api/feed";
import { useSession } from "@/app/session";
import { AuthPhoto } from "@/components/AuthPhoto";
import { ScreenTop } from "@/components/ScreenTop";
import { Button } from "@/components/Button";
import { Icon } from "@/components/Icon";
import { QueryState } from "@/components/QueryState";
import { Sheet } from "@/components/Sheet";
import { StateView } from "@/components/StateView";
import { useToast } from "@/components/Toast";
import type { Role } from "@/domain/types";
import { ComposeSheet, type Kid } from "./ComposeSheet";
import { PhotoViewer, PostCard } from "./parts";
import { ChildAlbum } from "./ChildAlbum";

type TabKey = "class" | "org" | "album" | "mine";
const TABS: Record<Role, { key: TabKey; label: string }[]> = {
  parent: [{ key: "class", label: "우리 반" }, { key: "org", label: "원 전체" }, { key: "mine", label: "우리 아이" }],
  teacher: [{ key: "org", label: "원 소식" }, { key: "album", label: "앨범" }],
  director: [{ key: "org", label: "원 소식" }, { key: "album", label: "앨범" }],
};
type Me = { children: { id: string; display_name: string; classroom_id: string }[] };

/**
 * 소식(피드)과 앨범 (API 38~49 [제안]). 사진 AI가 없어서 올리는 사람이 아이를 직접 고른다.
 * 반 칸은 그 반 보호자만 읽고 쓰고(교사는 403), 원 칸은 같은 원 교직원과 보호자가 쓴다.
 */
export function FeedScreen({ role }: { role: Role }) {
  const { user } = useSession();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const tabs = TABS[role];
  const tab = (tabs.find((t) => t.key === params.get("tab"))?.key ?? tabs[0].key) as TabKey;

  const me = useQuery({ queryKey: ["me"], queryFn: () => api<Me>("/api/v1/me"), enabled: role === "parent" });
  const classKids = useChildren(role === "teacher" ? user?.classroom_ids[0] : undefined);
  const myKids = me.data?.children ?? [];
  const kids: Kid[] = role === "parent" ? myKids : (classKids.data ?? []);

  const classLane: Lane | undefined = role === "parent" && myKids[0] ? { kind: "class", id: myKids[0].classroom_id } : undefined;
  const orgLane: Lane | undefined = user ? { kind: "org", id: user.org_id } : undefined;
  const lane = tab === "class" ? classLane : orgLane;

  const posts = usePosts(tab === "album" ? undefined : lane);
  const album = useAlbum(tab === "album" ? lane : undefined);
  const del = useDeletePost();
  const hide = useHidePost();

  const [compose, setCompose] = useState(false);
  const [viewer, setViewer] = useState<{ photos: Photo[]; index: number } | null>(null);
  const [confirm, setConfirm] = useState<{ kind: "delete" | "hide"; post: Post } | null>(null);

  const audience = role === "parent" ? "parent" : "staff";
  const laneLabel = tab === "class" ? "우리 반 소식" : "원 전체 소식";
  const waiting = role === "parent" ? [me] : [];

  const actionOf = (p: Post) => {
    if (p.author_id === user?.id) return { label: "삭제", run: () => setConfirm({ kind: "delete", post: p }) };
    if (role === "director" && p.lane === "org") return { label: "숨기기", run: () => setConfirm({ kind: "hide", post: p }) };
    return undefined;
  };
  const doConfirm = () => {
    if (!confirm) return;
    const { kind, post } = confirm;
    const run = kind === "delete" ? del : hide;
    run.mutate(post.id, {
      onSuccess: () => { setConfirm(null); toast({ kind: "ok", title: kind === "delete" ? "글을 지웠어요" : "글을 숨겼어요" }); },
      onError: () => { setConfirm(null); toast({ kind: "error", title: kind === "delete" ? "글을 지우지 못했어요" : "글을 숨기지 못했어요", sub: "연결을 확인하고 다시 눌러 주세요" }); },
    });
  };

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-8">
      <ScreenTop
        audience={role === "parent" ? "parent" : "staff"}
        back={role === "teacher" ? { to: "/teacher/home", label: "홈" } : undefined}
        title={role === "parent" ? "사진" : "원 소식"}
        sub={role === "parent" ? "우리 반과 원의 소식, 우리 아이 사진을 볼 수 있어요" : "원 전체에 올라온 이야기와 사진이에요"}
        right={
          tab === "mine" ? undefined : <button type="button" disabled={!lane} onClick={() => setCompose(true)} className="mr-1 inline-flex h-10 items-center gap-1.5 rounded-full bg-brand-fill px-4 text-callout font-semibold text-on-brand active:scale-95 disabled:opacity-50">
            <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden><path d="M4 8a2 2 0 0 1 2-2h1.5l1.2-1.6A1 1 0 0 1 9.5 4h5a1 1 0 0 1 .8.4L16.5 6H18a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" /><circle cx="12" cy="12.5" r="3.2" /></svg>
            올리기
          </button>
        }
      />
      <div className="mb-4" />

      <div role="tablist" aria-label="사진 구성" className="mb-4 grid grid-flow-col gap-1 rounded-md bg-fill p-1">
        {tabs.map((t) => (
          <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => setParams({ tab: t.key }, { replace: true })} className={`h-9 rounded-sm text-footnote font-semibold ${tab === t.key ? "bg-card shadow-card" : "text-ink2"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "mine" ? (
        <ChildAlbum embedded />
      ) : tab === "album" ? (
        <>
          <QueryState queries={[...waiting, album]} skeleton={3} errorTitle="앨범을 불러오지 못했어요">
            {album.data && album.data.length > 0 ? (
              <ul className="grid grid-cols-3 gap-1 overflow-hidden rounded-lg">
                {album.data.map((p, i) => (
                  <li key={p.id}>
                    <button type="button" onClick={() => setViewer({ photos: album.data!, index: i })} aria-label={`사진 ${i + 1}장 크게 보기`} className="block w-full active:opacity-80">
                      <AuthPhoto photo={p} className="aspect-square w-full" />
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              <StateView kind="empty" audience={audience} title="아직 사진이 없어요" sub="글에 사진을 올리면 여기에 모여요" />
            )}
          </QueryState>
        </>
      ) : (
        <>
        {tab === "class" && (
          <p className="mb-3 flex items-start gap-2 rounded-lg bg-card p-3 text-footnote text-ink2 shadow-card">
            <Icon name="lock" className="mt-0.5 size-4 shrink-0" />
            <span className="break-keep">우리 반 부모님끼리만 보는 칸이에요. 선생님·원장님은 이 칸을 볼 수 없어요. 원에 할 말은 요청으로 보내 주세요.</span>
          </p>
        )}
        <QueryState queries={[...waiting, posts]} skeleton={3} errorTitle="소식을 불러오지 못했어요">
          {posts.data && posts.data.length > 0 ? (
            <div className="grid gap-3">
              {posts.data.map((p) => (
                <PostCard key={p.id} post={p} mine={p.author_id === user?.id} action={actionOf(p)} onOpenPhoto={(i) => setViewer({ photos: p.photos, index: i })} />
              ))}
            </div>
          ) : (
            <StateView kind="empty" audience={audience} title="아직 올라온 소식이 없어요" sub="첫 글을 올려 보세요" />
          )}
        </QueryState>
        </>
      )}

      <ComposeSheet open={compose} onClose={() => setCompose(false)} lane={lane} kids={kids} laneLabel={laneLabel} />
      {viewer && <PhotoViewer photos={viewer.photos} index={viewer.index} onIndex={(i) => setViewer({ ...viewer, index: i })} onClose={() => setViewer(null)} />}
      <Sheet open={!!confirm} onClose={() => setConfirm(null)} title={confirm?.kind === "hide" ? "이 글을 숨길까요?" : "이 글을 지울까요?"}>
        <p className="text-footnote text-ink2">{confirm?.kind === "hide" ? "숨기면 모두에게 보이지 않아요." : "올린 사진도 함께 지워지고 되돌릴 수 없어요."}</p>
        <Button variant="danger" loading={del.isPending || hide.isPending} onClick={doConfirm}>{confirm?.kind === "hide" ? "숨기기" : "지우기"}</Button>
        <Button variant="plain" size="sm" onClick={() => setConfirm(null)}>취소</Button>
      </Sheet>
    </div>
  );
}
