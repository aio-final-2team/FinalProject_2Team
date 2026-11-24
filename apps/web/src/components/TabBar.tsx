import { NavLink } from "react-router";
import { Icon } from "./Icon";

export type TabItem = { to: string; icon: string; label: string; count?: number };

/**
 * 아래 탭 바 (교사·원장·학부모 공통). 숫자 배지, 가운데 큰 버튼(center), 누르면 시트를 여는 칸(extra)을 지원한다.
 * className으로 너비 제한(학부모 480)이나 PC에서 숨김(교사·원장 lg:hidden)을 정한다.
 */
export function TabBar({ items, center, extra, className = "" }: { items: TabItem[]; center?: { to: string; label: string }; extra?: { icon: string; label: string; onClick: () => void }; className?: string }) {
  const cell = "relative grid justify-items-center gap-0.5 text-caption font-semibold";
  const left = center ? items.slice(0, Math.ceil(items.length / 2)) : items;
  const right = center ? items.slice(Math.ceil(items.length / 2)) : [];
  const tab = (it: TabItem) => (
    <NavLink key={it.to} to={it.to} className={({ isActive }) => `${cell} ${isActive ? "text-accent" : "text-ink2"}`}>
      <span className="relative">
        <Icon name={it.icon} className="size-6" />
        {!!it.count && <span className="absolute -right-2.5 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-caption font-bold text-on-accent ring-2 ring-card">{it.count}</span>}
      </span>
      {it.label}
    </NavLink>
  );
  return (
    <nav className={`glass fixed inset-x-0 bottom-0 z-30 mx-auto grid grid-flow-col items-end bg-bar pb-[max(10px,env(safe-area-inset-bottom))] pt-2 shadow-[0_-1px_0_var(--sep)] backdrop-blur-xl backdrop-saturate-[1.8] ${className}`} aria-label="주 메뉴">
      {left.map(tab)}
      {center && (
        <NavLink to={center.to} aria-label={center.label} className="grid justify-items-center">
          <span className="-mt-5 grid size-[52px] place-items-center rounded-full bg-brand-fill text-on-brand shadow-float active:scale-95">
            <Icon name="plus" className="size-6" />
          </span>
          <span className="sr-only">{center.label}</span>
        </NavLink>
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
