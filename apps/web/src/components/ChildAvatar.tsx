import { usePhotoUrl } from "@/api/feed";

/** 서버가 아이 정보에 붙여 주는 프로필 사진. 없으면 이름 끝 글자를 보여 준다 */
export type ProfilePhoto = { file_url: string } | null | undefined;

type Look = { name: string; size: number; tone: "fill" | "tint"; textClass: string; rounded: string };

function Initial({ name, size, tone, textClass, rounded }: Look) {
  return (
    <span aria-hidden style={{ width: size, height: size }} className={`grid shrink-0 place-items-center font-bold ${rounded} ${textClass} ${tone === "tint" ? "bg-tint text-accent-ink" : "bg-fill"}`}>
      {name.slice(-1)}
    </span>
  );
}

function PhotoAvatar({ url, ...look }: Look & { url: string }) {
  const q = usePhotoUrl(url);
  if (q.data) return <img src={q.data} alt={`${look.name} 프로필 사진`} draggable={false} style={{ width: look.size, height: look.size }} className={`shrink-0 object-cover ${look.rounded}`} />;
  if (q.isLoading) return <span aria-busy="true" style={{ width: look.size, height: look.size }} className={`skel shrink-0 ${look.rounded}`} />;
  return <Initial {...look} />; /* 사진을 못 받으면 글자로 돌아간다 */
}

/**
 * 아이 동그라미 (관찰 기록·알림장 목록·우리 아이). 프로필 사진이 있으면 사진을, 없으면 이름 끝 글자를 보여 준다.
 * 받는 동안은 흐린 칸이다.
 */
export function ChildAvatar({ name, photo, size = 40, tone = "fill", textClass = "text-callout", rounded = "rounded-full" }: { name: string; photo?: ProfilePhoto; size?: number; tone?: "fill" | "tint"; textClass?: string; rounded?: string }) {
  const look: Look = { name, size, tone, textClass, rounded };
  return photo?.file_url ? <PhotoAvatar url={photo.file_url} {...look} /> : <Initial {...look} />;
}
