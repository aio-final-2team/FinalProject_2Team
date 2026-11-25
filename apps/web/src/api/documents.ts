import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "./client";

/** 자료 (API 28·29, 문서 3.23). 상세에 본문 조각(chunks)이 온다. suspicious는 보안 검사에서 걸려 검색·답변에서 빠지는 조각 */
export type Chunk = { index: number; location: string | null; content: string; suspicious: boolean };
export type Doc = { id: string; title: string; doc_type: string; status: string; effective_from: string; effective_to: string | null; ingest_status: string; chunk_count: number; chunks?: Chunk[] };

export const DOC_TYPE_LABEL: Record<string, string> = { notice: "가정통신문", menu: "식단표", schedule: "일정", policy: "운영 규정", consult_timetable: "상담 시간표", law: "법령", public_data: "공공 자료" };

export const useDocuments = () => useQuery({ queryKey: ["documents"], queryFn: () => api<{ items: Doc[] }>("/api/v1/documents?size=100").then((r) => r.items) });
export const useDocument = (id?: string) => useQuery({ queryKey: ["document", id], queryFn: () => api<{ document: Doc }>(`/api/v1/documents/${id}`).then((r) => r.document), enabled: !!id });

export const VISIBILITY_LABEL: Record<string, string> = { all: "모두", parents: "보호자만", staff: "교직원만" };
/** 서버가 읽을 수 있는 글 파일 (문서 3.22): .md·.markdown·.txt UTF-8, 2MiB 이하 */
export const DOC_FILE_TYPES = ".md,.markdown,.txt";
export const MAX_DOC_BYTES = 2 * 1024 * 1024;

/** 자료 올리기 (API 27). 새 자료는 202, 같은 파일이 이미 있으면 200 + 기존 자료. 적재 결과는 응답의 ingest_status(succeeded·failed) */
export function useUploadDocument() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (v: { file: File; doc_type: string; visibility: string; classroom_ids: string[]; effective_from: string }) => {
      const f = new FormData();
      f.set("file", v.file);
      f.set("doc_type", v.doc_type);
      f.set("visibility", v.visibility);
      v.classroom_ids.forEach((c) => f.append("classroom_ids", c));
      f.set("effective_from", v.effective_from);
      return api<{ document: Doc }>("/api/v1/documents", { method: "POST", body: f }).then((r) => r.document);
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["documents"] }),
  });
}
