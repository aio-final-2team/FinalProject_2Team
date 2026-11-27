import { useState } from "react";
import { Link, Outlet, useLocation, useNavigate } from "react-router";
import { MeSheet } from "@/components/MeSheet";
import { TabBar, tabOn } from "@/components/TabBar";
import { useCards } from "@/api/cards";
import { useNotes } from "@/api/notes";
import { todayKST } from "@/domain/notes";
import { useSession } from "@/app/session";
import { MainLogo, SymbolMark } from "@/components/Brand";
import { Icon } from "@/components/Icon";
import type { Role } from "@/domain/types";

/**
 * 교사·원장 화면 틀. 웹 우선: 1024px 이상은 왼쪽 메뉴, 그보다 좁으면 아래 탭 바.
 * 원장은 MVP에서 받은함 하나라 아래 탭 바를 숨긴다.
 */
export function StaffLayout({ role }: { role: Exclude<Role, "parent"> }) {
  const { signOut, user } = useSession();
  const nav = useNavigate();
  const { data } = useCards("review");
  const notes = useNotes(role === "teacher" ? user?.classroom_ids[0] : undefined, todayKST());
  const review = data?.counts.review ?? 0;
  const noteLeft = notes.data?.filter((n) => n.status === "needs_check").length ?? 0;
  const base = `/${role}`;
  /* 11/27까지 교사 탭은 홈 · 알림장 (문의는 따로, 11/20 제안) */
  const items =
    role === "teacher"
      ? [
          { to: `${base}/home`, icon: "home", label: "홈", count: 0, also: [`${base}/care`, `${base}/class`, `${base}/feed`, `${base}/memory`, `${base}/notifications`, `${base}/soon`] },
          { to: `${base}/notes`, icon: "document", label: "알림장", count: noteLeft },
          { to: `${base}/inbox`, icon: "inbox", label: "받은함", count: review },
        ]
      : [
          { to: `${base}/overview`, icon: "home", label: "현황", count: 0, also: [`${base}/care`, `${base}/notifications`] },
          { to: `${base}/inbox`, icon: "inbox", label: "받은함", count: review },
          { to: `${base}/feed`, icon: "class", label: "원 소식", count: 0 },
        ];
  const [me, setMe] = useState(false);
  const { pathname } = useLocation();

  return (
    <div className={`min-h-full lg:grid lg:grid-cols-[232px_1fr] ${role === "teacher" ? "[--tab-lift:20px] lg:[--tab-lift:0px]" : ""}`}>
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 border-r border-sep bg-card px-4 py-6 lg:flex">
        <div className="px-2">
          <MainLogo className="h-10" />
        </div>
        <div className="px-2 text-sub text-ink2">{user?.display_name ?? (role === "teacher" ? "선생님" : "원장")}</div>
        <nav className="grid gap-1" aria-label="주 메뉴">
          {items.map((it) => (
            <Link
              key={it.to}
              to={it.to}
              aria-current={tabOn(pathname, it) ? "page" : undefined}
              className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-body font-semibold transition-colors ${tabOn(pathname, it) ? "bg-tint text-accent-ink" : "text-ink hover:bg-fill"}`}
            >
              <Icon name={it.icon} className="size-5" />
              <span className="flex-1">{it.label}</span>
              {it.count > 0 && <span className="rounded-full bg-accent px-2 text-cap font-bold text-on-accent tabular-nums">{it.count}</span>}
            </Link>
          ))}
        </nav>
        {role === "teacher" && (
          <Link to={`${base}/ask`} aria-current={tabOn(pathname, { to: `${base}/ask` }) ? "page" : undefined} className={`flex items-center gap-3 rounded-xl px-3 py-2.5 text-body font-semibold transition-colors ${tabOn(pathname, { to: `${base}/ask` }) ? "bg-tint text-accent-ink" : "text-ink hover:bg-fill"}`}>
            <SymbolMark motion="curious" className="size-5" />
            AI에게 묻기
          </Link>
        )}
        <button
          className="mt-auto flex items-center gap-3 rounded-xl px-3 py-2.5 text-sub text-ink2 hover:bg-fill"
          onClick={() => {
            signOut();
            nav("/login");
          }}
        >
          <Icon name="logout" className="size-5" />
          로그아웃
        </button>
      </aside>

      <main className="min-w-0 pb-[calc(76px+env(safe-area-inset-bottom)+var(--tab-lift,0px))] lg:pb-0">
        <Outlet />
      </main>

      <MeSheet open={me} onClose={() => setMe(false)} />
      <TabBar center={role === "teacher" ? { to: `${base}/ask`, label: "AI에게 묻기", mascot: true } : undefined} className="max-w-none lg:hidden" items={items.map((it) => ({ to: it.to, icon: it.icon, label: it.label, count: it.count, also: it.also }))} extra={{ icon: "profile", label: "내 정보", onClick: () => setMe(true) }} />
    </div>
  );
}
