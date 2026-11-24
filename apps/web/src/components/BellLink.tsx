import { Link } from "react-router";
import { useNotifications } from "@/api/notifications";
import { Icon } from "./Icon";

/** 알림 목록으로 가는 벨. 안 읽은 알림 수를 숫자로 보여 준다 (API 11). */
export function BellLink({ to }: { to: string }) {
  const { data } = useNotifications();
  const unread = data?.items.filter((n) => !n.read_at).length ?? 0;
  return (
    <Link to={to} className="relative grid size-11 place-items-center rounded-md text-ink" aria-label={unread ? `알림, 안 읽은 알림 ${unread}개` : "알림"}>
      <Icon name="bell" className="size-6" />
      {unread > 0 && (
        <span className="absolute right-1 top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-caption font-bold tabular-nums text-on-accent ring-2 ring-g">
          {unread > 9 ? "9+" : unread}
        </span>
      )}
    </Link>
  );
}
