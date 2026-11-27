import { useSyncExternalStore } from "react";

/** 화면 모드. 고르지 않으면 기기 설정을 따른다(tokens.css). 고르면 이 브라우저에 기억한다 */
export type Theme = "light" | "dark";
export const THEME_KEY = "yuchion.theme";

const media = () => window.matchMedia("(prefers-color-scheme: dark)");
const saved = (): Theme | null => {
  try {
    const v = localStorage.getItem(THEME_KEY);
    return v === "light" || v === "dark" ? v : null;
  } catch {
    return null;
  }
};
const listeners = new Set<() => void>();

/** 지금 보이는 모드 */
export const currentTheme = (): Theme => {
  const forced = document.documentElement.dataset.theme;
  if (forced === "light" || forced === "dark") return forced;
  return media().matches ? "dark" : "light";
};

export function applySavedTheme() {
  const t = saved();
  if (t) document.documentElement.dataset.theme = t;
}

export function setTheme(t: Theme) {
  document.documentElement.dataset.theme = t;
  try {
    localStorage.setItem(THEME_KEY, t);
  } catch {
    /* 저장이 막혀도 이번 화면에서는 바뀐다 */
  }
  listeners.forEach((l) => l());
}

export function useTheme() {
  const theme = useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      const m = media();
      m.addEventListener("change", cb);
      return () => {
        listeners.delete(cb);
        m.removeEventListener("change", cb);
      };
    },
    currentTheme,
  );
  return { theme, toggle: () => setTheme(theme === "dark" ? "light" : "dark") };
}
