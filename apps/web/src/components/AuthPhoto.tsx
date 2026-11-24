import { usePhotoUrl, type Photo } from "@/api/feed";

/** 로그인 토큰으로 받은 사진. 받는 동안 흐린 칸, 못 받으면 안내 문구를 보여 준다 */
export function AuthPhoto({ photo, className = "", fit = "cover", alt = "올린 사진" }: { photo: Pick<Photo, "file_url">; className?: string; fit?: "cover" | "contain"; alt?: string }) {
  const q = usePhotoUrl(photo.file_url);
  if (q.isLoading) return <div aria-busy="true" className={`skel ${className}`} />;
  if (q.isError || !q.data) return <div role="img" aria-label="사진을 불러오지 못했어요" className={`grid place-items-center bg-fill px-2 text-center text-caption text-ink2 ${className}`}>사진을 불러오지 못했어요</div>;
  return <img src={q.data} alt={alt} draggable={false} className={`${fit === "contain" ? "object-contain" : "object-cover"} ${className}`} />;
}
