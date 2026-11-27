import { Link } from "react-router";
import { kstDate, useCalendar, type CalendarItem } from "@/api/staff";
import { QueryState } from "@/components/QueryState";
import { ScreenTop } from "@/components/ScreenTop";
import { StateView } from "@/components/StateView";
import { dateLabel } from "@/domain/notes";

const DAYS = 45;
/** 문서에서 일정을 찾은 위치. 본문이면 알려 줄 게 없어서 숨긴다 */
const place = (i: CalendarItem) => (i.location === "본문" || /^\d+\s*쪽$/.test(i.location) ? "" : i.location);

/** 원 일정. 오늘부터 45일 동안 원 자료에 적힌 일정을 날짜순으로 보여 준다 */
export function CalendarPage() {
  const from = kstDate();
  const to = kstDate(DAYS);
  const q = useCalendar(from, to);
  const days = new Map<string, CalendarItem[]>();
  (q.data ?? []).forEach((i) => days.set(i.date, [...(days.get(i.date) ?? []), i]));

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop back={{ to: "/teacher/home", label: "홈" }} title="원 일정" sub={`${dateLabel(from)}부터 ${DAYS}일 동안의 일정이에요`} />
      <QueryState queries={[q]} skeleton={3} errorTitle="일정을 불러오지 못했어요">
        {days.size === 0 ? (
          <div className="mt-6">
            <StateView kind="empty" audience="staff" title="이 기간에 등록된 일정이 없어요" sub={"원 자료에 일정이 올라오면\n여기에 보여요"} />
          </div>
        ) : (
          [...days].map(([date, items]) => (
            <section key={date} className="mt-5" aria-label={dateLabel(date)}>
              <h2 className="mb-2 px-1 text-footnote font-semibold text-ink2">{dateLabel(date)}</h2>
              <ul className="overflow-hidden rounded-lg bg-card shadow-card [&>li+li]:border-t [&>li+li]:border-sep">
                {items.map((i) => (
                  <li key={`${i.document_id}-${i.title}`} className="px-3 py-3">
                    <b className="block break-keep text-callout font-semibold">{i.title}</b>
                    <span className="mt-0.5 block break-keep text-footnote text-ink2">
                      {i.end_date && i.end_date !== i.date ? `${dateLabel(i.end_date)}까지` : null}
                      {i.end_date && i.end_date !== i.date && place(i) ? ", " : null}
                      {place(i)}
                    </span>
                    <Link to={`/teacher/class/${i.document_id}`} className="mt-1 inline-block text-caption font-semibold text-accent-ink">
                      {i.document_title}
                    </Link>
                  </li>
                ))}
              </ul>
            </section>
          ))
        )}
      </QueryState>
    </div>
  );
}
