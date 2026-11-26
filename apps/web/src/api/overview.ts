import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

/** 원장 현황 (API 21, 문서 3.18) */
export type Overview = {
  unassigned: number;
  waiting: number;
  delayed: number;
  done_today: number;
  completed_unconfirmed: number;
  reassignments: { card_id: string; from: string | null; to: string; reason: string; at: string }[];
  eval: { suite: string; requested_model: string; returned_model: string | null; passed: number; total: number; started_at: string }[];
};

export const useOverview = () => useQuery({ queryKey: ["overview"], queryFn: () => api<Overview>("/api/v1/overview"), refetchInterval: 60_000 });
