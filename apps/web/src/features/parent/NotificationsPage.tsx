import { useNavigate } from "react-router";
import { useNotifications, useReadNotification, type Notification } from "@/api/notifications";
import { Buddy } from "@/components/Brand";
import { NotificationGroups, NotificationRow } from "@/components/NotificationRow";
import { ScreenTop } from "@/components/ScreenTop";
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
      <ScreenTop audience="parent" back={{ to: "/parent/home", label: "홈" }} title="알림" sub={`${items.filter((n) => !n.read_at).length}개 안 읽음`} />
      <div className="mb-4" />
      <QueryState queries={[list]} skeleton={3} errorTitle="알림을 불러오지 못했어요">
      {!items.length ? (
        <div className="grid justify-items-center gap-2 py-12 text-center">
          <Buddy face="waiting" className="size-20" />
          <b className="text-headline">새 알림이 없어요</b>
        </div>
      ) : (
        <NotificationGroups items={items} renderRow={(n) => <NotificationRow key={n.id} n={n} onOpen={() => open(n)} />} />
      )}
      </QueryState>
    </div>
  );
}
