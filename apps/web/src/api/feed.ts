import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, fetchBlobUrl } from "./client";

/** 피드·앨범 (API 38~49, 문서 3.29 [제안]). 글에는 작성자 이름이 없고 author_id만 온다 */
export type Photo = { id: string; post_id: string; media_type: string; size_bytes: number; created_at: string; file_url: string };
export type Post = { id: string; lane: "class" | "org"; classroom_id: string | null; author_id: string; body: string; status: "published" | "hidden"; created_at: string; photos: Photo[] };
export type Lane = { kind: "class" | "org"; id: string };
export type PhotoScope = "family" | "class" | "org";
type Page<T> = { items: T[]; total: number; page: number; size: number };

/** 서버 규칙: 사진 0~10장, 장당 5MiB, 형식은 jpeg·png·webp */
export const MAX_PHOTOS = 10;
export const MAX_PHOTO_BYTES = 5 * 1024 * 1024;
export const PHOTO_TYPES = ["image/jpeg", "image/png", "image/webp"];

const base = (l: Lane) => `/api/v1/${l.kind === "class" ? "classrooms" : "organizations"}/${l.id}`;

export const usePosts = (l?: Lane) =>
  useQuery({ queryKey: ["feed", "posts", l?.kind, l?.id], queryFn: () => api<Page<Post>>(`${base(l!)}/posts?size=50`).then((r) => r.items), enabled: !!l });

export const useAlbum = (l?: Lane, childId?: string) =>
  useQuery({
    queryKey: ["feed", "album", l?.kind, l?.id, childId ?? "all"],
    queryFn: () => api<Page<Photo>>(`${base(l!)}/albums?size=100${childId ? `&child_id=${childId}` : ""}`).then((r) => r.items),
    enabled: !!l,
  });

/** 올린 사람이 아이를 직접 표시한다(사진 AI 전). tags는 파일 순서대로 아이 ID 배열 */
export function useCreatePost(l?: Lane) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { body: string; files: File[]; tags: string[][] }) => {
      const f = new FormData();
      f.set("body", v.body);
      v.files.forEach((x) => f.append("files", x));
      f.set("child_ids", JSON.stringify(v.tags));
      return api<{ post: Post }>(`${base(l!)}/posts`, { method: "POST", body: f });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feed"] }),
  });
}

export function useDeletePost() {
  const qc = useQueryClient();
  return useMutation({ mutationFn: (id: string) => api<void>(`/api/v1/posts/${id}`, { method: "DELETE" }), onSuccess: () => qc.invalidateQueries({ queryKey: ["feed"] }) });
}

/** 원장만, 원 칸 글만 숨길 수 있다 */
export function useHidePost() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api<{ post: Post }>(`/api/v1/posts/${id}`, { method: "PATCH", body: JSON.stringify({ status: "hidden" }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feed"] }),
  });
}

export const usePhotoScope = (childId?: string) =>
  useQuery({ queryKey: ["feed", "scope", childId], queryFn: () => api<{ child_id: string; photo_scope: PhotoScope }>(`/api/v1/children/${childId}/photo-scope`), enabled: !!childId });

export function useSetPhotoScope(childId?: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (photo_scope: PhotoScope) => api<{ child_id: string; photo_scope: PhotoScope }>(`/api/v1/children/${childId}/photo-scope`, { method: "PATCH", body: JSON.stringify({ photo_scope }) }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["feed"] }),
  });
}

/** 사진 한 장을 토큰 붙여 받아 브라우저 임시 주소로 바꾼다. 한 번 받으면 다시 받지 않는다 */
export const usePhotoUrl = (fileUrl: string) => useQuery({ queryKey: ["photo", fileUrl], queryFn: () => fetchBlobUrl(fileUrl), enabled: !!fileUrl, staleTime: Infinity, gcTime: 10 * 60_000, retry: 1 });
