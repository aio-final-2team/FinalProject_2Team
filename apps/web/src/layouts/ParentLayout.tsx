import { NavLink, Outlet } from "react-router";
import { Icon } from "@/components/Icon";

/** 학부모 화면 틀. 모바일 웹이 기준이고, PC에서는 가운데 앱 폭(480px)으로 보인다. 탭: 홈, 요청, 소식 */
export function ParentLayout() {
  const tabs = [
    { to: "/parent/home", icon: "home", label: "홈" },
    { to: "/parent/requests", icon: "inquiry", label: "요청" },
    { to: "/parent/feed", icon: "class", label: "소식" },
  ];
  return (
    <div className="mx-auto min-h-full max-w-[480px] bg-g pb-[calc(76px+env(safe-area-inset-bottom))] lg:my-6 lg:min-h-[calc(100dvh-48px)] lg:rounded-[28px] lg:shadow-[0_20px_60px_-30px_rgba(11,31,58,.35)]">
      <Outlet />
      <nav className="glass fixed inset-x-0 bottom-0 z-30 mx-auto grid max-w-[480px] grid-flow-col bg-bar pb-[max(10px,env(safe-area-inset-bottom))] pt-2 shadow-[0_-1px_0_var(--sep)] backdrop-blur-xl backdrop-saturate-[1.8]" aria-label="주 메뉴">
        {tabs.map((t) => (
          <NavLink key={t.to} to={t.to} className={({ isActive }) => `grid justify-items-center gap-0.5 text-[10.5px] font-medium ${isActive ? "text-accent" : "text-ink3"}`}>
            <Icon name={t.icon} className="size-6" />
            {t.label}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
