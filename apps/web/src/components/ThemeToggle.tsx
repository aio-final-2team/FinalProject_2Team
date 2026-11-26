import { useEffect, useState } from "react";
import { useTheme } from "@/app/theme";

/** 아래에 붙은 막대(탭 바, 아래 고정 버튼 칸) 가운데 가장 높은 막대의 위쪽 가장자리까지 높이(px). 없으면 0 */
const barLift = () => {
  let lift = 0;
  document.querySelectorAll<HTMLElement>("[data-bottom-bar]").forEach((el) => {
    if (getComputedStyle(el).position !== "fixed") return;
    const r = el.getBoundingClientRect();
    if (r.height > 0 && r.width > 0) lift = Math.max(lift, window.innerHeight - r.top);
  });
  return Math.round(lift);
};

/** 모든 화면 오른쪽 아래에 떠 있는 라이트·다크 전환 버튼. 아래 막대가 있으면 그 바로 위로 올라간다 */
export function ThemeToggle() {
  const { theme, toggle } = useTheme();
  const [lift, setLift] = useState(0);
  useEffect(() => {
    let raf = 0;
    const measure = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setLift(barLift()));
    };
    measure();
    const mo = new MutationObserver(measure);
    mo.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
    window.addEventListener("resize", measure);
    return () => {
      cancelAnimationFrame(raf);
      mo.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, []);
  const dark = theme === "dark";
  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "라이트 모드로 바꾸기" : "다크 모드로 바꾸기"}
      style={{ bottom: lift ? `${lift + 12}px` : "calc(env(safe-area-inset-bottom) + 16px)" }}
      className="glass fixed right-3 z-[60] grid size-10 place-items-center rounded-full border border-sep bg-bar text-ink shadow-card backdrop-blur-xl transition-[transform,bottom] duration-200 active:scale-95 lg:right-5"
    >
      {dark ? (
        <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
        </svg>
      )}
    </button>
  );
}
