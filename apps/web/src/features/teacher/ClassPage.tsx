import { ScreenTop } from "@/components/ScreenTop";
import { Link } from "react-router";
import { useState } from "react";
import { useDocuments, type Doc } from "@/api/documents";
import { menuWeek, useNextMeal } from "@/api/meals";
import { useSession } from "@/app/session";
import { Icon } from "@/components/Icon";
import { QueryState } from "@/components/QueryState";
import { MealRepresentative } from "@/components/MealRepresentative";
import { UploadSheet } from "./UploadSheet";
import { dateLabel, todayKST } from "@/domain/notes";


/** 식단표와 가정통신문 (API 28·29 자료). 식단은 식단표 본문 표에서 오늘 또는 가장 가까운 날짜를 읽어 점심·오후 간식으로 나눠 보여 준다. */
export function ClassPage() {
  const { user } = useSession();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const meal = useNextMeal(date).data;
  const docs = useDocuments();
  const active = (type: string) => (docs.data ?? []).filter((d) => d.doc_type === type && d.status === "active").sort((a, b) => b.effective_from.localeCompare(a.effective_from));
  const menuDocs = active("menu").filter((d) => !d.title.startsWith("가상"));
  const weekly = menuDocs.filter((d) => menuWeek(d));
  const weeks = weekly.filter((d) => menuWeek(d)!.end >= date).sort((a, b) => menuWeek(a)!.start.localeCompare(menuWeek(b)!.start));
  const past = weekly.filter((d) => menuWeek(d)!.end < date).sort((a, b) => menuWeek(b)!.start.localeCompare(menuWeek(a)!.start));
  const guides = menuDocs.filter((d) => !menuWeek(d));
  const notices = active("notice");
  const [up, setUp] = useState(false);
  const [morePast, setMorePast] = useState(false);
  const [moreNotice, setMoreNotice] = useState(false);
  const FOLD = 4;

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop back={{ to: "/teacher/home", label: "홈" }} title="식단표와 가정통신문" sub={dateLabel(date)} />
      <button type="button" onClick={() => setUp(true)} className="mt-3 inline-flex h-10 items-center rounded-md bg-tint px-4 text-callout font-semibold text-accent-ink active:scale-[.97]">자료 올리기</button>
      <UploadSheet open={up} onClose={() => setUp(false)} classroomId={cid} />

      <QueryState queries={[docs]} skeleton={2}>
        <Group title={meal && !meal.today ? "다음 식단" : "오늘 식단"} empty="등록된 식단표가 없어요" count={(meal ? 1 : 0) + weeks.length}>
          {meal && (
            <li className="px-3 py-3">
              <span className="text-caption font-bold text-accent-ink">{meal.label}</span>
              <dl className="mt-1.5 grid grid-cols-[4.5rem_1fr] gap-x-3 gap-y-1.5 text-callout">
                <dt className="font-bold text-ink2">점심</dt>
                <dd className="font-semibold">{meal.lunch}</dd>
                {meal.snack && (
                  <>
                    <dt className="font-bold text-ink2">오후 간식</dt>
                    <dd className="font-semibold">{meal.snack}</dd>
                  </>
                )}
              </dl>
              <MealRepresentative date={meal.date} mealText={meal.lunch} />
            </li>
          )}
          {weeks.map((d) => <DocRow key={d.id} d={d} week={menuWeek(d)!} />)}
        </Group>
        {past.length > 0 && (
          <Group title="지난 식단표" empty="" count={past.length}>
            {(morePast ? past : past.slice(0, FOLD)).map((d) => <DocRow key={d.id} d={d} week={menuWeek(d)!} />)}
            {past.length > FOLD && <li><button type="button" onClick={() => setMorePast((v) => !v)} className="h-11 w-full text-footnote font-semibold text-accent-ink">{morePast ? "접기" : `${past.length - FOLD}건 더 보기`}</button></li>}
          </Group>
        )}
        {guides.length > 0 && (
          <Group title="식단 안내" empty="" count={guides.length}>
            {guides.map((d) => <DocRow key={d.id} d={d} />)}
          </Group>
        )}
        <Group title="가정통신문" empty="등록된 가정통신문이 없어요" count={notices.length}>
          {(moreNotice ? notices : notices.slice(0, FOLD)).map((d) => <DocRow key={d.id} d={d} />)}
          {notices.length > FOLD && <li><button type="button" onClick={() => setMoreNotice((v) => !v)} className="h-11 w-full text-footnote font-semibold text-accent-ink">{moreNotice ? "접기" : `${notices.length - FOLD}개 더 보기`}</button></li>}
        </Group>
      </QueryState>
      
    </div>
  );
}

function Group({ title, empty, count, children }: { title: string; empty: string; count: number; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h2 className="mb-2 px-1 text-footnote font-semibold text-ink2">{title}</h2>
      {count > 0 ? <ul className="overflow-hidden rounded-lg bg-card shadow-card [&>li+li]:border-t [&>li+li]:border-sep">{children}</ul> : <p className="rounded-lg bg-card p-4 text-center text-callout text-ink2 shadow-card">{empty}</p>}
    </section>
  );
}

function DocRow({ d, week }: { d: Doc; week?: { start: string; end: string } }) {
  return (
    <li>
      <Link to={`/teacher/class/${d.id}`} className="flex items-center gap-3 px-3 py-3 active:bg-fill">
        <span className="grid size-9 shrink-0 place-items-center rounded-md bg-fill"><Icon name="document" className="size-5" /></span>
        <span className="min-w-0 flex-1">
          <b className="block truncate text-callout">{d.title}</b>
          <span className="text-caption text-ink2">{week ? `${week.start.slice(5).replace("-", "/")} ~ ${week.end.slice(5).replace("-", "/")}` : `${d.effective_from}부터${d.effective_to ? ` ${d.effective_to}까지` : ""}`}</span>
        </span>
        <Icon name="chevR" className="size-4 shrink-0 text-ink2" />
      </Link>
    </li>
  );
}
