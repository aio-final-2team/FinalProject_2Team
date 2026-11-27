import { useQuery } from "@tanstack/react-query";
import { api } from "./client";

/** API 76: 그날 급식 참고 사진. 우리 원 식단표 점심을 바탕으로 만든 가상 사진이고, 없으면 null */
export type MealPhoto = { meal_date: string; main_dish: string; file_url: string };

export const useMealPhoto = (date?: string) =>
  useQuery({
    queryKey: ["meal-photo", date],
    queryFn: () => api<{ items: MealPhoto[] }>(`/api/v1/meal-photos?from=${date}&to=${date}`).then((r) => r.items[0] ?? null),
    enabled: !!date,
    staleTime: 60 * 60_000,
  });
