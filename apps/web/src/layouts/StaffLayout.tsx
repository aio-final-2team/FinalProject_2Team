import { NavLink, Outlet, useNavigate } from "react-router";
import { useCards } from "@/api/cards";
import { useNotes } from "@/api/notes";
import { todayKST } from "@/domain/notes";
import { useSession } from "@/app/session";
import { Wordmark, SymbolMark } from "@/components/Brand";
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
          { to: `${base}/home`, icon: "home", label: "홈", count: 0 },
          { to: `${base}/records`, icon: "class", label: "관찰 기록", count: 0 },
          { to: `${base}/notes`, icon: "document", label: "알림장", count: noteLeft },
        ]
      : [{ to: `${base}/inbox`, icon: "inbox", label: "받은함", count: review }];

  return (
    <div className="min-h-full lg:grid lg:grid-cols-[232px_1fr]">
      <aside className="sticky top-0 hidden h-dvh flex-col gap-6 border-r border-sep bg-card px-4 py-6 lg:flex">
        <div className="flex items-center gap-2 px-2">
          <SymbolMark className="size-7" />
          <Wordmark className="h-[18px]" />
        </div>
        <div className="px-2 text-sub text-ink2">{user?.display_name ?? (role === "teacher" ? "선생님" : "원장")}</div>
        <nav className="grid gap-1" aria-label="주 메뉴">
          {items.map((it) => (
            <NavLink
              key={it.to}
              to={it.to}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-xl px-3 py-2.5 text-body font-semibold transition-colors ${isActive ? "bg-tint text-accent-ink" : "text-ink hover:bg-fill"}`
              }
            >
              <Icon name={it.icon} className="size-5" />
              <span className="flex-1">{it.label}</span>
              {it.count > 0 && <span className="rounded-full bg-accent px-2 text-cap font-bold text-on-accent tabular-nums">{it.count}</span>}
            </NavLink>
          ))}
        </nav>
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

      <main className="min-w-0 pb-[calc(76px+env(safe-area-inset-bottom))] lg:pb-0">
        <Outlet />
      </main>

      {items.length > 1 && (
        <nav className="glass fixed inset-x-0 bottom-0 z-30 grid grid-flow-col bg-bar pb-[max(10px,env(safe-area-inset-bottom))] pt-2 shadow-[0_-1px_0_var(--sep)] backdrop-blur-xl backdrop-saturate-[1.8] lg:hidden" aria-label="주 메뉴">
          {items.map((it) => (
            <NavLink key={it.to} to={it.to} className={({ isActive }) => `relative grid justify-items-center gap-0.5 text-caption font-semibold ${isActive ? "text-accent" : "text-ink2"}`}>
              <span className="relative">
                <Icon name={it.icon} className="size-6" />
                {it.count > 0 && <span className="absolute -right-2.5 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-accent px-1 text-caption font-bold text-on-accent ring-2 ring-card">{it.count}</span>}
              </span>
              {it.label}
            </NavLink>
          ))}
        </nav>
      )}
    </div>
  );
}
