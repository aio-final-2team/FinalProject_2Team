import { useQuery } from "@tanstack/react-query";

const ROOT = "https://raw.githubusercontent.com/aio-final-2team/FinalProject_2Team/develop/data/fixtures/public_meals/";
const DATA = `${ROOT}public-meals-2026-06-to-12.json`;

type PublicMeal = {
  date: string;
  institution: string;
  lunch: string[];
  representative_image?: { file: string; main_dish: string; generation_tool: string };
};

export type MealRepresentative = { fileUrl: string; mainDish: string; institution: string; exactDate: boolean };

const words = (value: string) => value.match(/[가-힣]{2,}/g) ?? [];

function select(items: PublicMeal[], date: string, mealText: string): MealRepresentative | null {
  const pictured = items.filter((item) => item.representative_image);
  const exact = pictured.find((item) => item.date === date);
  const tokens = words(mealText);
  const similar = pictured
    .map((item) => ({ item, score: tokens.filter((word) => [...item.lunch, item.representative_image!.main_dish].join(" ").includes(word)).length }))
    .filter(({ score }) => score > 0)
    .sort((a, b) => b.score - a.score)[0]?.item;
  const item = exact ?? similar;
  if (!item?.representative_image) return null;
  return {
    fileUrl: new URL(item.representative_image.file, ROOT).href,
    mainDish: item.representative_image.main_dish,
    institution: item.institution,
    exactDate: item.date === date,
  };
}

/** 서버 식단 이미지 API가 생기기 전까지 저장소의 공개 대표 이미지와 날짜·메뉴를 임시 연결한다. */
export const useMealRepresentative = (date: string, mealText?: string) =>
  useQuery({
    queryKey: ["public-meal-representative", date, mealText],
    queryFn: async () => {
      const response = await fetch(DATA);
      if (!response.ok) throw new Error("대표 식단 데이터를 불러오지 못했어요");
      return select((await response.json()) as PublicMeal[], date, mealText ?? "");
    },
    enabled: !!mealText,
    staleTime: 24 * 60 * 60_000,
    retry: 1,
  });
