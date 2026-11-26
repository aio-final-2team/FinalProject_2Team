import { useTheme } from "@/app/theme";

/** 모든 화면 위쪽 가운데에 떠 있는 라이트·다크 전환 버튼. 브랜드 마크(왼쪽)와 알림·내 정보(오른쪽)를 피한다 */
export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const dark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "라이트 모드로 바꾸기" : "다크 모드로 바꾸기"}
      className="glass fixed left-1/2 top-[max(8px,env(safe-area-inset-top))] z-[60] grid size-9 -translate-x-1/2 place-items-center rounded-full border border-sep bg-bar text-ink shadow-card backdrop-blur-xl transition-transform active:scale-95 lg:top-3"
    >
      {dark ? (
        <svg viewBox="0 0 24 24" className="size-[18px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="size-[18px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}
