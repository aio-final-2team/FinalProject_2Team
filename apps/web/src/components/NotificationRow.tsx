import { useState, type ReactNode } from "react";
import { Icon } from "./Icon";
import { fmtDate } from "@/domain/datetime";
import type { Notification } from "@/api/notifications";
import { term } from "@/domain/wording";

/** 알림 종류별 아이콘 (서버 kind). 모르는 종류는 받은함 아이콘 */
export const KIND_ICON: Record<string, string> = {
  new_card: "inbox", urgent_complaint: "urgent", uncertain_complaint: "urgent", parent_message: "inquiry", reassigned: "profile",
  care_requested: "medication", care_confirmed: "approve", care_rejected: "reject", cancelled: "reject", completed: "approve",
  consultation_booked: "consult", consultation_ending: "pending", consultation_delayed: "pending",
  note_sent: "document", note_corrected: "document", sent_or_booked: "inquiry",
};

/**
 * 알림이 무슨 일인지 알려 주는 말머리. 종류로 정해지면 그 말, 문의·상담·민원처럼 종류만으로는 모르는 것은
 * 요청 유형(requestType: "문의"·"상담"·"민원"·"투약"·"귀가")으로 채운다. 모르면 말머리를 달지 않는다.
 */
const KIND_TAG: Record<string, string> = {
  note_sent: "알림장", note_corrected: "알림장",
  consultation_booked: "상담", consultation_ending: "상담", consultation_delayed: "상담", slot_hold_expired: "상담",
  care_requested: "투약·귀가", care_confirmed: "투약·귀가", care_rejected: "투약·귀가", cancelled: "투약·귀가",
  director_report: "원장 보고", urgent_complaint: "긴급", uncertain_complaint: "판단 필요", reassigned: "담당 변경",
};
export const notificationTag = (n: Notification, requestType?: string) => KIND_TAG[n.kind] ?? requestType;

/** 교사·원장·학부모 알림 목록이 같이 쓰는 한 줄. 안 읽은 알림은 파란 점과 굵은 제목 */
export function NotificationRow({ n, line, tag, onOpen }: { n: Notification; line?: string | null; tag?: string; onOpen: () => void }) {
  const unread = !n.read_at;
  return (
    <li className="[&+&]:border-t [&+&]:border-sep">
      <button type="button" onClick={onOpen} className="flex min-h-14 w-full items-center gap-3 px-3 py-2.5 text-left active:bg-fill">
        <span aria-hidden className={`size-2 shrink-0 rounded-full ${unread ? "bg-accent" : "bg-transparent"}`} />
        <span aria-hidden className={`grid size-9 shrink-0 place-items-center rounded-md ${unread ? "bg-tint text-accent-ink" : "bg-fill text-ink2"}`}><Icon name={KIND_ICON[n.kind] ?? "inbox"} className="size-5" /></span>
        <span className="min-w-0 flex-1">
          <b className={`block text-callout ${unread ? "font-semibold" : "font-medium text-ink2"}`}>{tag && !n.title.includes(tag) && <Tag>{tag}</Tag>}{term(n.title)}</b>
          {(n.body ?? line) && <span className="block truncate text-footnote text-ink2">{term(n.body ?? line)}</span>}
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
export function NotificationGroups({ items, renderRow, tagOf }: { items: Notification[]; renderRow: (n: Notification) => ReactNode; tagOf?: (n: Notification) => string | undefined }) {
  const groups: Notification[][] = [];
  const index = new Map<string, number>();
  for (const n of items) {
    const key = `${n.kind}\u0000${n.title}\u0000${tagOf?.(n) ?? ""}`;
    const at = index.get(key);
    if (at === undefined) { index.set(key, groups.length); groups.push([n]); } else groups[at].push(n);
  }
  return (
    <ul className="overflow-hidden rounded-lg bg-card shadow-card">
      {groups.map((g) => (g.length === 1 ? renderRow(g[0]) : <Group key={g[0].id} items={g} renderRow={renderRow} tag={tagOf?.(g[0])} />))}
    </ul>
  );
}

function Group({ items, renderRow, tag }: { items: Notification[]; renderRow: (n: Notification) => ReactNode; tag?: string }) {
  const [open, setOpen] = useState(false);
  const first = items[0];
  const unread = items.filter((n) => !n.read_at).length;
  return (
    <li className="[&+&]:border-t [&+&]:border-sep">
      <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="flex min-h-14 w-full items-center gap-3 px-3 py-2.5 text-left active:bg-fill">
        <span aria-hidden className={`size-2 shrink-0 rounded-full ${unread ? "bg-accent" : "bg-transparent"}`} />
        <span aria-hidden className={`grid size-9 shrink-0 place-items-center rounded-md ${unread ? "bg-tint text-accent-ink" : "bg-fill text-ink2"}`}><Icon name={KIND_ICON[first.kind] ?? "inbox"} className="size-5" /></span>
        <span className="min-w-0 flex-1">
          <b className={`block text-callout ${unread ? "font-semibold" : "font-medium text-ink2"}`}>{tag && !first.title.includes(tag) && <Tag>{tag}</Tag>}{term(first.title)} <span className="tabular-nums">{items.length}건</span></b>
          <span className="block truncate text-footnote text-ink2">{unread ? `안 읽음 ${unread}건` : "모두 읽었어요"}</span>
        </span>
        <time className="shrink-0 text-caption text-ink2 tabular-nums">{fmtDate(first.deliver_after)}</time>
        <span aria-hidden className={`shrink-0 text-ink2 transition-transform ${open ? "rotate-90" : ""}`}>›</span>
      </button>
      {open && <ul className="border-t border-sep bg-g/50">{items.map((n) => renderRow(n))}</ul>}
    </li>
  );
}

/** 제목 앞의 작은 말머리(상담·귀가·투약·알림장 같은 무슨 일인지) */
function Tag({ children }: { children: ReactNode }) {
  return <span className="mr-1.5 inline-block rounded-sm bg-fill px-1.5 py-0.5 align-[1px] text-caption font-semibold text-ink2">{children}</span>;
}
