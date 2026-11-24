import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

/** 자료 (API 28·29, 문서 3.23). 상세에 본문 조각(chunks)이 온다. suspicious는 보안 검사에서 걸려 검색·답변에서 빠지는 조각 */
export type Chunk = { index: number; location: string | null; content: string; suspicious: boolean };
export type Doc = { id: string; title: string; doc_type: string; status: string; effective_from: string; effective_to: string | null; ingest_status: string; chunk_count: number; chunks?: Chunk[] };

export const DOC_TYPE_LABEL: Record<string, string> = { notice: "가정통신문", menu: "식단표", schedule: "일정", policy: "운영 규정", consult_timetable: "상담 시간표", law: "법령", public_data: "공공 자료" };

export const useDocuments = () => useQuery({ queryKey: ["documents"], queryFn: () => api<{ items: Doc[] }>("/api/v1/documents?size=100").then((r) => r.items) });
export const useDocument = (id?: string) => useQuery({ queryKey: ["document", id], queryFn: () => api<{ document: Doc }>(`/api/v1/documents/${id}`).then((r) => r.document), enabled: !!id });
