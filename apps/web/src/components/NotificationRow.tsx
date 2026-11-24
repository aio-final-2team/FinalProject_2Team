import { Icon } from "./Icon";
import type { Notification } from "@/api/notifications";

/** 알림 종류별 아이콘 (서버 kind). 모르는 종류는 받은함 아이콘 */
const KIND_ICON: Record<string, string> = {
  new_card: "inbox", urgent_complaint: "urgent", uncertain_complaint: "urgent", parent_message: "inquiry", reassigned: "profile",
  care_requested: "medication", care_confirmed: "approve", care_rejected: "reject", cancelled: "reject", completed: "approve",
  consultation_booked: "consult", consultation_ending: "pending", consultation_delayed: "pending",
  note_sent: "document", note_corrected: "document", sent_or_booked: "inquiry",
};

/** 교사·원장·학부모 알림 목록이 같이 쓰는 한 줄. 안 읽은 알림은 파란 점과 굵은 제목 */
export function NotificationRow({ n, line, onOpen }: { n: Notification; line?: string | null; onOpen: () => void }) {
  const unread = !n.read_at;
  return (
    <li className="[&+&]:border-t [&+&]:border-sep">
      <button type="button" onClick={onOpen} className="flex min-h-14 w-full items-center gap-3 px-3 py-2.5 text-left active:bg-fill">
        <span aria-hidden className={`size-2 shrink-0 rounded-full ${unread ? "bg-accent" : "bg-transparent"}`} />
        <span aria-hidden className={`grid size-9 shrink-0 place-items-center rounded-md ${unread ? "bg-tint text-accent-ink" : "bg-fill text-ink2"}`}><Icon name={KIND_ICON[n.kind] ?? "inbox"} className="size-5" /></span>
        <span className="min-w-0 flex-1">
          <b className={`block text-callout ${unread ? "font-semibold" : "font-medium text-ink2"}`}>{n.title}</b>
          {(n.body ?? line) && <span className="block truncate text-footnote text-ink2">{n.body ?? line}</span>}
        </span>
        <time className="shrink-0 text-caption text-ink2 tabular-nums">{new Date(n.deliver_after).toLocaleDateString("ko-KR", { month: "numeric", day: "numeric" })}</time>
      </button>
    </li>
  );
}
