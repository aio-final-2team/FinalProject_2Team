import { Link } from "react-router";
import { useDocument, useDocuments } from "@/api/documents";
import { usePosts } from "@/api/feed";
import { pickNotice, plain, useNextMeal } from "@/api/meals";
import { useMealRepresentative } from "@/api/publicMeals";
import { useSession } from "@/app/session";
import { AuthPhoto } from "@/components/AuthPhoto";
import { Icon } from "@/components/Icon";
import { todayKST } from "@/domain/notes";

const md = (iso: string) => `${Number(iso.slice(5, 7))}/${Number(iso.slice(8, 10))}`;
/** 통신문 본문 조각의 앞 두 줄을 한 줄로 잇는다(제목·표 줄은 건너뛰고 목록 기호는 뗀다) */
const firstLine = (text?: string) =>
  (text ?? "")
    .split("\n")
    .map((l) => plain(l.replace(/^\s*[-*]\s+/, "")))
    .filter((l) => l && !l.startsWith("#") && !l.startsWith("|"))
    .slice(0, 2)
    .join(" · ")
    .slice(0, 90);

/** 홈 '오늘 우리 반': 급식(오늘 또는 가장 가까운 날짜)·가정통신문 한 건·반 활동(가장 최근 소식)과 각 이미지 */
export function TodayClass() {
  const { user } = useSession();
  const date = todayKST();
  const meal = useNextMeal(date).data;
  const mealImg = useMealRepresentative(meal?.date ?? date, meal?.lunch).data;
  const docs = useDocuments();
  const notice = pickNotice(docs.data, date);
  const noticeBody = useDocument(notice?.id).data;
  const posts = usePosts(user ? { kind: "org", id: user.org_id } : undefined).data;
  const latest = (posts ?? []).filter((p) => p.status === "published").sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
  const photo = latest?.photos[0];
  const when = latest ? (latest.created_at.slice(0, 10) === date ? "오늘" : md(latest.created_at.slice(0, 10))) : "";
  const line = firstLine(noticeBody?.chunks?.[0]?.content);

  return (
    <section aria-label="오늘 우리 반" className="mt-4">
      <h2 className="mb-2 px-1 text-footnote font-semibold text-ink2">오늘 우리 반</h2>
      <ul className="overflow-hidden rounded-xl bg-tint shadow-card [&>li+li]:border-t [&>li+li]:border-card/60">
        <li>
          <Link to="/teacher/class" className="flex items-center gap-3 p-3.5 active:bg-card/40">
            <span className="min-w-0 flex-1">
              <b className="text-footnote text-accent-ink">급식{meal ? ` · ${meal.today ? "오늘" : meal.label}` : ""}</b>
              <span className="mt-0.5 block text-callout">{meal ? `점심 ${meal.lunch}` : "등록된 식단이 없어요"}</span>
              {meal?.snack && <span className="block text-footnote text-ink2">오후 간식 {meal.snack}</span>}
            </span>
            {mealImg && <img src={mealImg.fileUrl} alt={`${mealImg.mainDish} 참고 이미지`} className="aspect-[4/3] w-24 shrink-0 rounded-lg object-cover" />}
            <Icon name="chevR" className="size-4 shrink-0 text-accent-ink" />
          </Link>
        </li>
        <li>
          <Link to={notice ? `/teacher/class/${notice.id}` : "/teacher/class"} className="flex items-center gap-3 p-3.5 active:bg-card/40">
            <span className="min-w-0 flex-1">
              <b className="text-footnote text-accent-ink">가정통신문</b>
              <span className="mt-0.5 block truncate text-callout">{notice ? notice.title : "등록된 가정통신문이 없어요"}</span>
              {line && <span className="line-clamp-2 text-footnote text-ink2">{line}</span>}
            </span>
            <Icon name="chevR" className="size-4 shrink-0 text-accent-ink" />
          </Link>
        </li>
        <li>
          <Link to="/teacher/feed" className="flex items-center gap-3 p-3.5 active:bg-card/40">
            <span className="min-w-0 flex-1">
              <b className="text-footnote text-accent-ink">반 활동{when ? ` · ${when}` : ""}</b>
              <span className="mt-0.5 line-clamp-2 block text-callout">{latest ? latest.body : "올라온 소식이 아직 없어요"}</span>
            </span>
            {photo && <AuthPhoto photo={photo} className="aspect-[4/3] w-24 shrink-0 overflow-hidden rounded-lg" />}
            <Icon name="chevR" className="size-4 shrink-0 text-accent-ink" />
          </Link>
        </li>
      </ul>
    </section>
  );
}
