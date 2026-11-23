import { Link, useNavigate } from "react-router";
import { useCards } from "@/api/cards";
import { useNotifications, useReadNotification, type Notification } from "@/api/notifications";
import { SymbolMark } from "@/components/Brand";
import { Icon } from "@/components/Icon";

/** 교직원 알림 목록 (API 11). 카드·알림장 알림을 누르면 해당 화면으로 간다 */
export function TeacherNotifications({ role = "teacher" }: { role?: "teacher" | "director" }) {
  const nav = useNavigate();
  const list = useNotifications();
  const read = useReadNotification();
  const cards = useCards("review");
  const items = list.data?.items ?? [];
  const back = role === "teacher" ? "/teacher/home" : "/director/inbox";

  const open = (n: Notification) => {
    if (!n.read_at) read.mutate(n.id);
    if (n.subject_type === "daily_note") nav("/teacher/notes");
    else if (n.subject_type === "card" && n.subject_id) nav(`/${role}/inbox/${n.subject_id}`);
    else {
      /* 카드 알림은 subject_id가 없을 수 있어 요청 ID로 확인 필요 카드를 찾고, 없으면 받은함 목록으로 간다 */
      const card = n.request_id ? cards.data?.items.find((c) => c.requestId === n.request_id) : undefined;
      nav(card ? `/${role}/inbox/${card.id}` : `/${role}/inbox`);
    }
  };

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <Link to={back} className="inline-flex min-h-11 items-center gap-0.5 pt-2 text-body font-medium text-accent">
        <Icon name="chevL" className="size-4" />
        {role === "teacher" ? "홈" : "받은함"}
      </Link>
      <h1 className="text-large-title font-bold tracking-[-0.025em]">알림</h1>
      <p className="mb-4 mt-0.5 text-footnote font-medium text-ink2">{items.filter((n) => !n.read_at).length}개 안 읽음</p>
      {list.isLoading ? (
        <p className="py-10 text-center text-callout text-ink2">불러오는 중…</p>
      ) : list.isError ? (
        <p className="rounded-lg bg-danger-tint p-4 text-callout text-danger">알림을 불러오지 못했어요. 잠시 뒤 다시 열어 주세요.</p>
      ) : !items.length ? (
        <div className="grid justify-items-center gap-2 py-12 text-center">
          <SymbolMark className="size-16" />
          <b className="text-headline">새 알림이 없어요</b>
          <p className="text-callout text-ink2">퇴근 뒤에는 아이 안전 알림만 바로 와요.</p>
        </div>
      ) : (
        <ul className="overflow-hidden rounded-lg bg-card shadow-card">
          {items.map((n) => (
            <li key={n.id} className="[&+&]:border-t [&+&]:border-sep">
              <button onClick={() => open(n)} className="flex min-h-14 w-full items-center gap-3 px-3 py-2.5 text-left">
                <span aria-hidden className={`size-2 shrink-0 rounded-full ${n.read_at ? "bg-transparent" : "bg-accent"}`} />
                <span className="min-w-0 flex-1">
                  <b className={`block text-callout ${n.read_at ? "font-medium text-ink2" : "font-semibold"}`}>{n.title}</b>
                  {n.body && <span className="block truncate text-footnote text-ink2">{n.body}</span>}
                </span>
                <time className="shrink-0 text-caption text-ink2 tabular-nums">{new Date(n.deliver_after).toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" })}</time>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
