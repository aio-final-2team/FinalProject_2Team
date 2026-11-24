import { useEffect } from "react";
import { AuthPhoto } from "@/components/AuthPhoto";
import { Icon } from "@/components/Icon";
import type { Photo, Post } from "@/api/feed";

/** 사진 1장은 크게, 2장은 나란히, 3장 이상은 네 칸(넘치면 +N) */
export function PhotoGrid({ photos, onOpen }: { photos: Photo[]; onOpen: (index: number) => void }) {
  if (!photos.length) return null;
  const shown = photos.slice(0, 4);
  const cols = photos.length === 1 ? "grid-cols-1" : "grid-cols-2";
  return (
    <div className={`grid gap-1 overflow-hidden rounded-md ${cols}`}>
      {shown.map((p, i) => (
        <button key={p.id} type="button" onClick={() => onOpen(i)} aria-label={`사진 ${i + 1}장 크게 보기`} className="relative block overflow-hidden active:opacity-80">
          <AuthPhoto photo={p} className={`w-full ${photos.length === 1 ? "aspect-[4/3]" : "aspect-square"}`} />
          {i === 3 && photos.length > 4 && <span className="absolute inset-0 grid place-items-center bg-ink/55 text-headline font-bold text-card">+{photos.length - 4}</span>}
        </button>
      ))}
    </div>
  );
}

/** 사진 크게 보기. 좌우 버튼과 닫기 버튼, Esc 키 */
export function PhotoViewer({ photos, index, onIndex, onClose }: { photos: Photo[]; index: number; onIndex: (i: number) => void; onClose: () => void }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowLeft" && index > 0) onIndex(index - 1);
      if (e.key === "ArrowRight" && index < photos.length - 1) onIndex(index + 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [index, photos.length, onIndex, onClose]);
  const p = photos[index];
  if (!p) return null;
  const btn = "grid size-11 place-items-center rounded-full bg-card/90 text-ink active:scale-95";
  return (
    <div role="dialog" aria-modal="true" aria-label="사진 크게 보기" className="fixed inset-0 z-[70] grid grid-rows-[auto_1fr_auto] bg-ink">
      <div className="flex items-center justify-between px-3 pt-[max(12px,env(safe-area-inset-top))]">
        <span className="px-2 text-callout font-semibold tabular-nums text-card">{index + 1} / {photos.length}</span>
        <button type="button" onClick={onClose} aria-label="닫기" className={btn}>
          <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
        </button>
      </div>
      <div className="grid place-items-center overflow-hidden p-3">
        <AuthPhoto photo={p} fit="contain" className="max-h-full w-full max-w-[640px] rounded-md" />
      </div>
      <div className="flex items-center justify-center gap-4 pb-[max(16px,env(safe-area-inset-bottom))]">
        <button type="button" disabled={index === 0} onClick={() => onIndex(index - 1)} aria-label="이전 사진" className={`${btn} disabled:opacity-30`}><Icon name="chevL" className="size-5" /></button>
        <button type="button" disabled={index === photos.length - 1} onClick={() => onIndex(index + 1)} aria-label="다음 사진" className={`${btn} disabled:opacity-30`}><Icon name="chevR" className="size-5" /></button>
      </div>
    </div>
  );
}

const when = (iso: string) => new Date(iso).toLocaleDateString("ko-KR", { month: "long", day: "numeric" });

/** 글 카드. 작성자 이름은 API에 없어서 '내 글' 또는 칸 이름으로 보여 준다 */
export function PostCard({ post, mine, onOpenPhoto, action }: { post: Post; mine: boolean; onOpenPhoto: (i: number) => void; action?: { label: string; run: () => void } }) {
  return (
    <article className="rounded-lg bg-card p-3 shadow-card">
      <header className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-footnote">
          <b className={mine ? "text-accent-ink" : ""}>{mine ? "내 글" : post.lane === "class" ? "우리 반 보호자" : "원 소식"}</b>
          <time className="text-ink2">{when(post.created_at)}</time>
        </span>
        {action && (
          <button type="button" onClick={action.run} className="h-8 rounded-md px-2 text-footnote font-semibold text-ink2 active:scale-[.97]">{action.label}</button>
        )}
      </header>
      <p className="mt-1.5 whitespace-pre-line break-keep text-body">{post.body}</p>
      {post.photos.length > 0 && <div className="mt-2.5"><PhotoGrid photos={post.photos} onOpen={onOpenPhoto} /></div>}
    </article>
  );
}
