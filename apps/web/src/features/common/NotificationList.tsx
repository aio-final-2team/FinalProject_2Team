import { NotificationGroups, NotificationRow } from "@/components/NotificationRow";
import { ScreenTop } from "@/components/ScreenTop";
import { useNavigate } from "react-router";
import { QueryState, StaleBanner } from "@/components/QueryState";
import { useAllCards } from "@/api/cards";
import { useNotifications, useReadNotification, type Notification } from "@/api/notifications";
import { SymbolMark } from "@/components/Brand";
import { TYPE_LABEL } from "@/domain/status";

/** 교직원 알림 목록 (API 11). 카드·알림장 알림을 누르면 해당 화면으로 간다 */
export function TeacherNotifications({ role = "teacher" }: { role?: "teacher" | "director" }) {
  const nav = useNavigate();
  const list = useNotifications();
  const read = useReadNotification();
  const allCards = useAllCards();
  /* 알림에는 내용이 없어(title만) 요청 ID로 카드를 찾아 무슨 일인지 한 줄로 보여 준다 */
  const cardOf = (n: Notification) => (n.request_id ? allCards.find((c) => c.requestId === n.request_id) : undefined);
  const items = list.data?.items ?? [];
  const back = role === "teacher" ? "/teacher/home" : "/director/overview";

  /* 종류별로 가는 곳: 돌봄 요청·학부모 취소는 귀가·투약, 알림장은 알림장, 그 밖의 카드 알림은 요청 ID로 카드를 찾는다(상태가 달라도 찾는다) */
  const open = (n: Notification) => {
    if (!n.read_at) read.mutate(n.id);
    if (n.kind === "care_requested" || n.kind === "cancelled") nav(role === "teacher" ? "/teacher/care" : "/director/care");
    else if (n.subject_type === "daily_note") nav("/teacher/notes?tab=notes");
    else if (n.subject_type === "card" && n.subject_id) nav(`/${role}/inbox/${n.subject_id}`);
    else {
      const card = n.request_id ? allCards.find((c) => c.requestId === n.request_id) : undefined;
      nav(card ? `/${role}/inbox/${card.id}` : `/${role}/inbox`);
    }
  };

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop back={{ to: back, label: role === "teacher" ? "홈" : "현황" }} title="알림" sub={list.data ? `${items.filter((n) => !n.read_at).length}개 안 읽음` : " "} />
      <StaleBanner queries={[list]} />
      <div className="mb-4" />
      {list.isLoading || (list.isError && list.data === undefined) ? (
        <QueryState queries={[list]} errorTitle="알림을 불러오지 못했어요">{null}</QueryState>
      ) : !items.length ? (
        <div className="grid justify-items-center gap-2 py-12 text-center">
          <SymbolMark className="size-16" />
          <b className="text-headline">새 알림이 없어요</b>
          <p className="text-callout text-ink2">퇴근 뒤에는 아이 안전 알림만 바로 와요.</p>
        </div>
      ) : (
        <NotificationGroups
          items={items}
          renderRow={(n) => {
            const c = cardOf(n);
            return <NotificationRow key={n.id} n={n} line={c ? `${TYPE_LABEL[c.type]} · ${c.childName ? `${c.childName} · ` : ""}${c.title}` : null} onOpen={() => open(n)} />;
          }}
        />
      )}
    </div>
  );
}
