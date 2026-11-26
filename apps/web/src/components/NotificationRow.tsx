import { useState, type ReactNode } from "react";
import { Icon } from "./Icon";
import { fmtDate } from "@/domain/datetime";
import type { Notification } from "@/api/notifications";

/** 알림 종류별 아이콘 (서버 kind). 모르는 종류는 받은함 아이콘 */
export const KIND_ICON: Record<string, string> = {
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
        <time className="shrink-0 text-caption text-ink2 tabular-nums">{fmtDate(n.deliver_after)}</time>
      </button>
    </li>
  );
}

/**
 * 같은 종류·같은 제목의 알림이 둘 이상이면 한 줄로 묶는다. 누르면 펼쳐서 하나씩 열 수 있다.
 * 묶음 위치는 가장 최근 알림 기준이다(목록은 최신순).
 */
export function NotificationGroups({ items, renderRow }: { items: Notification[]; renderRow: (n: Notification) => ReactNode }) {
  const groups: Notification[][] = [];
  const index = new Map<string, number>();
  for (const n of items) {
    const key = `${n.kind}\u0000${n.title}`;
    const at = index.get(key);
    if (at === undefined) { index.set(key, groups.length); groups.push([n]); } else groups[at].push(n);
  }
  return (
    <ul className="overflow-hidden rounded-lg bg-card shadow-card">
      {groups.map((g) => (g.length === 1 ? renderRow(g[0]) : <Group key={g[0].id} items={g} renderRow={renderRow} />))}
    </ul>
  );
}

function Group({ items, renderRow }: { items: Notification[]; renderRow: (n: Notification) => ReactNode }) {
  const [open, setOpen] = useState(false);
  const first = items[0];
  const unread = items.filter((n) => !n.read_at).length;
  return (
    <li className="[&+&]:border-t [&+&]:border-sep">
      <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="flex min-h-14 w-full items-center gap-3 px-3 py-2.5 text-left active:bg-fill">
        <span aria-hidden className={`size-2 shrink-0 rounded-full ${unread ? "bg-accent" : "bg-transparent"}`} />
        <span aria-hidden className={`grid size-9 shrink-0 place-items-center rounded-md ${unread ? "bg-tint text-accent-ink" : "bg-fill text-ink2"}`}><Icon name={KIND_ICON[first.kind] ?? "inbox"} className="size-5" /></span>
        <span className="min-w-0 flex-1">
          <b className={`block text-callout ${unread ? "font-semibold" : "font-medium text-ink2"}`}>{first.title} <span className="tabular-nums">{items.length}건</span></b>
          <span className="block truncate text-footnote text-ink2">{unread ? `안 읽음 ${unread}건` : "모두 읽었어요"}</span>
        </span>
        <time className="shrink-0 text-caption text-ink2 tabular-nums">{fmtDate(first.deliver_after)}</time>
        <span aria-hidden className={`shrink-0 text-ink2 transition-transform ${open ? "rotate-90" : ""}`}>›</span>
      </button>
      {open && <ul className="border-t border-sep bg-g/50">{items.map((n) => renderRow(n))}</ul>}
    </li>
  );
}
