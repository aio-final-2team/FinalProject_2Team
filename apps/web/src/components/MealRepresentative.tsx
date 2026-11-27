import { useState } from "react";
import { usePhotoUrl } from "@/api/feed";
import { useMealPhoto } from "@/api/mealPhotos";

/** 식단표 점심 아래 급식 참고 사진. 서버(API 76·77)가 주는 사진만 보여 주고, 없으면 아무것도 그리지 않는다 */
export function MealRepresentative({ date }: { date: string }) {
  const meal = useMealPhoto(date).data;
  const src = usePhotoUrl(meal?.file_url ?? "").data;
  const [open, setOpen] = useState(false);
  if (!meal || !src) return null;
  const label = "급식 참고 사진";
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="relative mt-3 block w-full overflow-hidden rounded-xl bg-fill text-left active:opacity-90">
        <img src={src} alt={`${meal.main_dish} ${label}`} className="aspect-[4/3] w-full object-cover" />
        <span className="absolute left-2.5 top-2.5 rounded-full bg-ink/75 px-2.5 py-1 text-caption font-bold text-card">{label}</span>
      </button>
      <p className="mt-1.5 text-caption text-ink2">이날 식단표를 바탕으로 만든 참고 사진이에요 · {meal.main_dish}</p>
      {open && (
        <div role="dialog" aria-modal="true" aria-label="급식 참고 사진 크게 보기" className="fixed inset-0 z-[80] grid place-items-center bg-ink/95 p-4" onClick={() => setOpen(false)}>
          <button type="button" onClick={() => setOpen(false)} className="absolute right-4 top-[max(16px,env(safe-area-inset-top))] grid size-11 place-items-center rounded-full bg-card text-ink" aria-label="닫기">×</button>
          <img src={src} alt={`${meal.main_dish} ${label}`} className="max-h-full max-w-full rounded-xl object-contain" onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </>
  );
}
