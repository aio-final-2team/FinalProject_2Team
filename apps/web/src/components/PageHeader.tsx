import type { ReactNode } from "react";
import { Link } from "react-router";
import { SymbolMark } from "./Brand";
import { Icon } from "./Icon";

export function PageBack({ to, label }: { to: string; label: string }) {
  return (
    <Link to={to} className="inline-flex min-h-11 items-center gap-0.5 text-body font-medium text-accent">
      <Icon name="chevL" className="size-4" />
      {label}
    </Link>
  );
}

/** 교사 화면 공통 상단. 최상위 탭은 브랜드 행, 하위 화면은 동일한 뒤로가기를 쓴다. */
export function PageHeader({ title, meta, identity, back, backLabel, action }: { title: string; meta?: ReactNode; identity?: string; back?: string; backLabel?: string; action?: ReactNode }) {
  return (
    <header>
      {back ? (
        <PageBack to={back} label={backLabel ?? "뒤로"} />
      ) : (
        <div className="flex min-h-[52px] items-center justify-between pt-2">
          <SymbolMark className="size-8" />
          {action ?? <button className="grid size-11 place-items-center rounded-md text-ink" aria-label="알림"><Icon name="bell" className="size-6" /></button>}
        </div>
      )}
      {identity && <p className="mt-1 text-footnote font-semibold text-accent-ink">{identity}</p>}
      <h1 className="text-large-title font-bold tracking-[-0.025em]">{title}</h1>
      {meta && <p className="mt-0.5 text-footnote font-medium text-ink2">{meta}</p>}
    </header>
  );
}
