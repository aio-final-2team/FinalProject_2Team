import { useState } from "react";
import { useMealRepresentative } from "@/api/publicMeals";

export function MealRepresentative({ date, mealText }: { date: string; mealText: string }) {
  const image = useMealRepresentative(date, mealText);
  const [open, setOpen] = useState(false);
  if (!image.data) return null;
  const label = image.data.exactDate ? "대표 이미지" : "메뉴 참고 이미지";
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="relative mt-3 block w-full overflow-hidden rounded-xl bg-fill text-left active:opacity-90">
        <img src={image.data.fileUrl} alt={`${image.data.mainDish} ${label}`} className="aspect-[4/3] w-full object-cover" />
        <span className="absolute left-2.5 top-2.5 rounded-full bg-ink/75 px-2.5 py-1 text-caption font-bold text-card">{label}</span>
      </button>
      <p className="mt-1.5 text-caption text-ink2">공개 식단을 바탕으로 만든 참고 이미지예요 · {image.data.mainDish}</p>
      {open && (
        <div role="dialog" aria-modal="true" aria-label="식단 대표 이미지 크게 보기" className="fixed inset-0 z-[80] grid place-items-center bg-ink/95 p-4" onClick={() => setOpen(false)}>
          <button type="button" onClick={() => setOpen(false)} className="absolute right-4 top-[max(16px,env(safe-area-inset-top))] grid size-11 place-items-center rounded-full bg-card text-ink" aria-label="닫기">×</button>
          <img src={image.data.fileUrl} alt={`${image.data.mainDish} ${label}`} className="max-h-full max-w-full rounded-xl object-contain" onClick={(event) => event.stopPropagation()} />
        </div>
      )}
    </>
  );
}
