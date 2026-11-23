import type { ReactNode } from "react";
import { Icon } from "./Icon";

/**
 * 아래 고정 칸 (디자인 시스템 7.1). 반투명 바 안에 꽉 찬 주 버튼 하나.
 * 휴대폰에서는 아래 탭 바 바로 위, PC(1024 이상)에서는 본문 칸 아래에 붙는다.
 */
export function Dock({ children, reason, reasonIcon = "lock" }: { children: ReactNode; reason?: string; reasonIcon?: "lock" | "check" }) {
  return (
    <div className="glass fixed inset-x-0 bottom-[calc(64px+env(safe-area-inset-bottom))] z-20 border-t border-sep bg-bar px-4 py-2.5 backdrop-blur-xl lg:sticky lg:bottom-0 lg:mt-6">
      <div className="mx-auto grid max-w-[680px] gap-1.5">
        {reason && (
          <p className="flex items-center justify-center gap-1.5 text-footnote font-semibold text-ink2">
            <Icon name={reasonIcon} className="size-4" />
            {reason}
          </p>
        )}
        {children}
      </div>
    </div>
  );
}

/** 주 버튼: 높이 52, 모서리 8, 브랜드 블루 채움 (7.1). 잠기면 회색 */
export function PrimaryButton({ children, loading, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={rest.disabled || loading}
      aria-busy={loading || undefined}
      className={`flex h-[52px] w-full items-center justify-center gap-2 rounded-md text-body font-semibold transition-[transform,filter] duration-100 ease-out active:scale-[.97] active:brightness-95 disabled:scale-100 disabled:bg-fill2 disabled:text-ink2 disabled:brightness-100 bg-brand-fill text-on-brand ${rest.className ?? ""}`}
    >
      {loading && <span className="m-spin size-4 rounded-full border-2 border-current border-r-transparent" />}
      {children}
    </button>
  );
}

/** 보조 버튼: 연한 블루 또는 회색, 높이 44 (작은 것 32) */
export function SubButton({ tone = "tint", small, children, ...rest }: React.ButtonHTMLAttributes<HTMLButtonElement> & { tone?: "tint" | "gray"; small?: boolean }) {
  return (
    <button
      {...rest}
      className={`inline-flex items-center justify-center gap-1.5 rounded-md font-semibold transition-transform duration-100 active:scale-[.97] disabled:opacity-50 ${small ? "h-8 px-2.5 text-footnote" : "h-11 px-4 text-callout"} ${tone === "tint" ? "bg-tint text-accent-ink" : "bg-fill text-ink"} ${rest.className ?? ""}`}
    >
      {children}
    </button>
  );
}
