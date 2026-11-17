import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { Card, CardAction, Role } from "@/domain/types";
import { api } from "./client";

export const useCards = () => useQuery({ queryKey: ["cards"], queryFn: () => api<Card[]>("/api/cards") });

export const useCard = (id: string | undefined) =>
  useQuery({ queryKey: ["cards", id], queryFn: () => api<Card>(`/api/cards/${id}`), enabled: !!id });

/** 행동은 모두 한 번만 처리하는 키(Idempotency-Key)를 붙여 보낸다 (AC-05) */
export function useCardAction(id: string, role: Role) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ body, key }: { body: CardAction; key: string }) =>
      api<Card>(`/api/cards/${id}/actions`, {
        method: "POST",
        body: JSON.stringify(body),
        headers: { "Idempotency-Key": key, "X-Role": role },
      }),
    onSuccess: (card) => {
      qc.setQueryData(["cards", id], card);
      qc.setQueryData<Card[]>(["cards"], (list) => list?.map((c) => (c.id === id ? card : c)));
    },
  });
}

export const newKey = () => crypto.randomUUID();
