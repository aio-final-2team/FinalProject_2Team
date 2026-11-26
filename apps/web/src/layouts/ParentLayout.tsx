import { Link, Outlet, useLocation, useNavigate } from "react-router";
import { useState } from "react";
import { MeSheet } from "@/components/MeSheet";
import { TabBar, tabOn } from "@/components/TabBar";
import { Icon } from "@/components/Icon";
import { MainLogo } from "@/components/Brand";
import { useSession } from "@/app/session";

/** 학부모 공통 화면 틀. PC는 왼쪽 메뉴, 모바일은 아래 탭을 쓴다. */
export function ParentLayout() {
  const { user, signOut } = useSession();
  const nav = useNavigate();
  const { pathname } = useLocation();
  const [me, setMe] = useState(false);
  const items = [
    { to: "/parent/home", icon: "home", label: "홈", also: ["/parent/notifications", "/parent/ai"] },
    { to: "/parent/feed", icon: "photo", label: "사진" },
    { to: "/parent/requests", icon: "inquiry", label: "요청", not: ["/parent/requests/new"] },
  ];
  const desktopItems = [
    items[0],
    items[1],
    { to: "/parent/requests/new", icon: "write", label: "새 요청 쓰기" },
    items[2],
  ];
  return (
    <div className="min-h-full lg:grid lg:grid-cols-[232px_1fr]">
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 border-r border-sep bg-card px-4 py-6 lg:flex">
        <div className="px-2">
          <MainLogo className="h-10" />
        </div>
        <button type="button" onClick={() => setMe(true)} className="flex items-center gap-2 rounded-xl px-2 py-2 text-left text-sub text-ink2 hover:bg-fill">
          <Icon name="profile" className="size-5" />
          <span className="truncate">{user?.display_name ?? "보호자"}</span>
        </button>
        <nav className="grid gap-1" aria-label="주 메뉴">
          {desktopItems.map((it) => (
            <Link
              key={it.to}
              to={it.to}
              aria-current={tabOn(pathname, it) ? "page" : undefined}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-body font-semibold transition-colors ${tabOn(pathname, it) ? "bg-tint text-accent-ink" : "text-ink hover:bg-fill"}`}
            >
              <Icon name={it.icon} className="size-5" />
              {it.label}
            </Link>
          ))}
        </nav>
        <button
          className="mt-auto flex items-center gap-3 rounded-xl px-3 py-2.5 text-sub text-ink2 hover:bg-fill"
          onClick={() => { signOut(); nav("/login"); }}
        >
          <Icon name="logout" className="size-5" />
          로그아웃
        </button>
      </aside>

      <main className="min-w-0 pb-[calc(76px+env(safe-area-inset-bottom))] lg:pb-0">
        <Outlet />
      </main>

      <TabBar className="max-w-none lg:hidden" items={items} center={{ to: "/parent/requests/new", label: "새 요청 쓰기" }} extra={{ icon: "profile", label: "내 정보", onClick: () => setMe(true) }} />
      <MeSheet open={me} onClose={() => setMe(false)} />
    </div>
  );
}
