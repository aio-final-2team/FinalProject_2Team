import { useEffect, useState } from "react";
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

/** 몇 분 전·몇 시간 전, 하루가 지나면 날짜 */
function ago(iso: string) {
  const m = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  if (m < 1) return "방금 전";
  if (m < 60) return `${m}분 전`;
  if (m < 60 * 24) return `${Math.round(m / 60)}시간 전`;
  return new Date(iso).toLocaleDateString("ko-KR", { month: "long", day: "numeric" });
}

/** 사진 슬라이드: 옆으로 밀어 넘기고 오른쪽 위에 몇 번째인지 보여 준다. 누르면 크게 본다 */
export function PhotoCarousel({ photos, onOpen }: { photos: Photo[]; onOpen: (index: number) => void }) {
  const [at, setAt] = useState(0);
  /* 칸 비율은 첫 사진을 따르되 세로 4:5, 가로 1.91:1을 넘지 않게 한다(얼굴이 너무 잘리지 않도록) */
  const [ratio, setRatio] = useState(4 / 5);
  if (!photos.length) return null;
  return (
    <div className="relative">
      <ul
        className="flex snap-x snap-mandatory overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        onScroll={(e) => setAt(Math.round(e.currentTarget.scrollLeft / e.currentTarget.clientWidth))}
        aria-label="사진"
      >
        {photos.map((p, i) => (
          <li key={p.id} className="w-full shrink-0 snap-center" style={{ aspectRatio: ratio }}>
            <button type="button" onClick={() => onOpen(i)} aria-label={`사진 ${i + 1}장 크게 보기`} className="block size-full active:opacity-90">
              <AuthPhoto photo={p} className="size-full" onSize={i === 0 ? (w, h) => setRatio(Math.min(1.91, Math.max(4 / 5, w / h))) : undefined} />
            </button>
          </li>
        ))}
      </ul>
      {photos.length > 1 && <span aria-hidden className="pointer-events-none absolute right-3 top-3 rounded-full bg-ink/60 px-2 py-0.5 text-caption font-semibold tabular-nums text-card">{at + 1}/{photos.length}</span>}
    </div>
  );
}

/** 글 카드. 작성자 이름은 API에 없어서 '나' 또는 칸 이름으로 보여 준다. 더보기(⋯)는 지우기·숨기기처럼 할 수 있는 일이 있을 때만 나온다 */
export function PostCard({ post, mine, onOpenPhoto, action }: { post: Post; mine: boolean; onOpenPhoto: (i: number) => void; action?: { label: string; run: () => void } }) {
  const who = mine ? "나" : post.lane === "class" ? "우리 반 보호자" : "원 소식";
  return (
    <article className="overflow-hidden rounded-lg bg-card shadow-card">
      <header className="flex items-center gap-3 px-3 py-2.5">
        <span aria-hidden className={`grid size-10 shrink-0 place-items-center rounded-full text-callout font-bold ${mine ? "bg-tint text-accent-ink" : "bg-fill text-ink"}`}>{who.slice(0, 1)}</span>
        <span className="min-w-0 flex-1">
          <b className="block truncate text-callout">{who}</b>
          <time className="text-caption text-ink2">{ago(post.created_at)}</time>
        </span>
        {action && (
          <button type="button" onClick={action.run} aria-label={action.label} className="grid size-11 place-items-center rounded-full text-ink2 active:scale-95">
            <svg viewBox="0 0 24 24" className="size-5" fill="currentColor" aria-hidden><circle cx="5" cy="12" r="1.8" /><circle cx="12" cy="12" r="1.8" /><circle cx="19" cy="12" r="1.8" /></svg>
          </button>
        )}
      </header>
      <PhotoCarousel photos={post.photos} onOpen={onOpenPhoto} />
      <p className="whitespace-pre-line break-keep px-3 py-3 text-body">{post.body}</p>
    </article>
  );
}
