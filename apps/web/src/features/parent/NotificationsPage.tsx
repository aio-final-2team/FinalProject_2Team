import { Link, useNavigate } from "react-router";
import { useNotifications, useReadNotification, type Notification } from "@/api/notifications";
import { Buddy } from "@/components/Brand";
import { Icon } from "@/components/Icon";
import { QueryState } from "@/components/QueryState";

/** 학부모 알림 목록 (API 11). 알림장 알림(daily_note)을 누르면 홈의 오늘 알림장으로, 요청 알림은 요청 상세로 간다 */
export function NotificationsPage() {
  const nav = useNavigate();
  const list = useNotifications();
  const read = useReadNotification();
  const items = list.data?.items ?? [];

  const open = (n: Notification) => {
    if (!n.read_at) read.mutate(n.id);
    if (n.subject_type === "daily_note") nav("/parent/home");
    else if (n.request_id) nav(`/parent/requests/${n.request_id}`);
  };

  return (
    <div className="px-4 pb-8">
      <Link to="/parent/home" className="inline-flex min-h-11 items-center gap-0.5 pt-2 text-body font-medium text-accent">
        <Icon name="chevL" className="size-4" />홈
      </Link>
      <h1 className="text-large-title font-bold tracking-[-0.025em]">알림</h1>
      <p className="mb-4 mt-0.5 text-footnote font-medium text-ink2">{items.filter((n) => !n.read_at).length}개 안 읽음</p>
      <QueryState queries={[list]} skeleton={3} errorTitle="알림을 불러오지 못했어요">
      {!items.length ? (
        <div className="grid justify-items-center gap-2 py-12 text-center">
          <Buddy face="waiting" className="size-20" />
          <b className="text-headline">새 알림이 없어요</b>
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
      </QueryState>
    </div>
  );
}
