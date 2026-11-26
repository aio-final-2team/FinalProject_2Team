import { Link, useLocation } from "react-router";
import { Icon } from "./Icon";

/** also: 이 탭 아래에 두는 다른 주소(탭에 없는 화면). not: 같은 앞부분이어도 이 탭이 아닌 주소 */
export type TabItem = { to: string; icon: string; label: string; count?: number; also?: string[]; not?: string[] };

const under = (path: string, base: string) => path === base || path.startsWith(`${base}/`);
/** 들어간 화면에서도 그 화면이 속한 탭을 켜 둔다 */
export const tabOn = (path: string, it: Pick<TabItem, "to" | "also" | "not">) =>
  !it.not?.some((n) => under(path, n)) && (under(path, it.to) || !!it.also?.some((a) => under(path, a)));

/**
 * 아래 탭 바 (교사·원장·학부모 공통). 숫자 배지, 가운데 큰 버튼(center), 누르면 시트를 여는 칸(extra)을 지원한다.
 * className으로 너비 제한(학부모 480)이나 PC에서 숨김(교사·원장 lg:hidden)을 정한다.
 */
export function TabBar({ items, center, extra, className = "" }: { items: TabItem[]; center?: { to: string; label: string }; extra?: { icon: string; label: string; onClick: () => void }; className?: string }) {
  const { pathname } = useLocation();
  const cell = "relative grid justify-items-center gap-0.5 text-caption font-semibold";
  const left = center ? items.slice(0, Math.ceil(items.length / 2)) : items;
  const right = center ? items.slice(Math.ceil(items.length / 2)) : [];
  const tab = (it: TabItem) => (
    <Link key={it.to} to={it.to} aria-current={tabOn(pathname, it) ? "page" : undefined} className={`${cell} ${tabOn(pathname, it) ? "text-accent" : "text-ink2"}`}>
      <span className="relative">
        <Icon name={it.icon} className="size-6" />
        {!!it.count && <span className="absolute -right-2.5 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-caption font-bold text-on-accent ring-2 ring-card">{it.count}</span>}
      </span>
      {it.label}
    </Link>
  );
  return (
    <nav data-bottom-bar className={`glass fixed inset-x-0 bottom-0 z-30 mx-auto grid grid-flow-col items-end bg-bar pb-[max(10px,env(safe-area-inset-bottom))] pt-2 shadow-[0_-1px_0_var(--sep)] backdrop-blur-xl backdrop-saturate-[1.8] ${className}`} aria-label="주 메뉴">
      {left.map(tab)}
      {center && (
        <Link to={center.to} aria-label={center.label} className="grid justify-items-center">
          <span className="-mt-5 grid size-[52px] place-items-center rounded-full bg-brand-fill text-on-brand shadow-float active:scale-95">
            <Icon name="plus" className="size-6" />
          </span>
          <span className="sr-only">{center.label}</span>
        </Link>
      )}
      {right.map(tab)}
      {extra && (
        <button type="button" onClick={extra.onClick} className={`${cell} text-ink2`}>
          <Icon name={extra.icon} className="size-6" />
          {extra.label}
        </button>
      )}
    </nav>
  );
}
