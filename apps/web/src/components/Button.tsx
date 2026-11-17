import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon } from "./Icon";

type Variant = "primary" | "tinted" | "gray" | "plain" | "danger" | "navy";
const V: Record<Variant, string> = {
  primary: "bg-accent text-on-accent",
  tinted: "bg-tint text-accent-ink",
  gray: "bg-fill text-ink",
  plain: "bg-transparent text-accent",
  danger: "bg-danger text-white",
  navy: "bg-ink text-card",
};

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "md" | "sm";
  loading?: boolean;
  /** 잠긴 이유. 있으면 버튼 위에 보여 주고 버튼을 잠근다 */
  lockedReason?: string;
  icon?: string;
  children: ReactNode;
};

/** 누르는 순간 살짝 작아지고, 처리 중에는 잠겨서 두 번 눌리지 않는다 (AC-05) */
export function Button({ variant = "primary", size = "md", loading, lockedReason, icon, children, className = "", disabled, ...rest }: Props) {
  const locked = !!lockedReason;
  const btn = (
    <button
      {...rest}
      disabled={disabled || loading || locked}
      aria-busy={loading || undefined}
      className={`inline-flex items-center justify-center gap-1.5 rounded-xl font-semibold transition-[transform,filter] duration-200 ease-spring active:scale-[.97] active:brightness-95 disabled:active:scale-100 ${
        size === "md" ? "h-11 px-4 text-[15px]" : "h-8 px-3 text-[13px] rounded-[10px]"
      } ${locked || disabled ? "bg-fill text-ink3" : V[variant]} ${className}`}
    >
      {loading ? <span className="m-spin size-4 rounded-full border-2 border-current border-r-transparent" /> : locked ? <Icon name="lock" /> : icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  );
  if (!locked) return btn;
  return (
    <div className="grid gap-1.5">
      <p className="text-center text-sub text-ink2">{lockedReason}</p>
      {btn}
    </div>
  );
}
