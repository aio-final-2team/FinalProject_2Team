import { INTENT_LABEL, PARENT_LABEL, STAFF_LABEL, TYPE_LABEL, type RequestIntent, type RequestType, type Status, type Tone } from "@/domain/status";
import type { ReactNode } from "react";
import { Icon } from "./Icon";

/** 상태 색 = 브랜드 색: 할 일 블루 · 답 왔음 라벤더 · 완료 민트 · 기다림 회색 · 긴급 네이비 채움 */
const TONE: Record<Tone, string> = {
  action: "bg-tint text-accent-ink",
  answered: "bg-lav-tint text-lav",
  done: "bg-ok-tint text-ok",
  wait: "bg-fill text-ink2",
  urgent: "bg-ink text-card",
};

export function Pill({ tone = "wait", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 font-display text-cap font-semibold tracking-normal ${TONE[tone]}`}>{children}</span>;
}

export function StatusPill({ status, role }: { status: Status; role: "parent" | "staff" }) {
  const l = (role === "parent" ? PARENT_LABEL : STAFF_LABEL)[status];
  return <Pill tone={l.tone}>{l.label}</Pill>;
}

/** 요청 종류 이름표: 문의 블루 · 상담 민트 · 민원 라벤더 */
const TYPE_STYLE: Record<RequestType, { cls: string; icon: string }> = {
  inquiry: { cls: "bg-type-q-tint text-type-q", icon: "inquiry" },
  consult: { cls: "bg-type-c-tint text-type-c", icon: "consult" },
  complaint: { cls: "bg-type-m-tint text-type-m", icon: "complaint" },
};

export function TypeTag({ type, size = "md" }: { type: RequestType; size?: "sm" | "md" | "lg" }) {
  const s = TYPE_STYLE[type];
  const sz = size === "sm" ? "text-[10.5px] px-2 py-px" : size === "lg" ? "text-[13px] px-3 py-1.5" : "text-[11.5px] px-2 py-1";
  return (
    <span className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full font-display font-bold tracking-normal ${s.cls} ${sz}`}>
      <Icon name={s.icon} className={size === "lg" ? "size-[15px]" : "size-[13px]"} />
      {TYPE_LABEL[type]}
    </span>
  );
}

/** 요청 의도 배지(알림 회색 · 부탁 라벤더). 알림장 줄 배지(#407)와 같은 모양이고, 값이 없으면 그리지 않는다 */
export function IntentTag({ intent }: { intent?: RequestIntent | null }) {
  if (!intent) return null;
  return <span className={`inline-block rounded-sm px-2 py-0.5 text-caption font-semibold ${intent === "ask" ? "bg-lav-tint text-lav" : "bg-g text-ink2"}`}>{INTENT_LABEL[intent]}</span>;
}

/** 목록 줄 왼쪽 아이콘 칸: 진할수록 급함 */
export function WeightIcon({ weight, icon }: { weight: "urgent" | "action" | "normal" | "done"; icon: string }) {
  const cls = { urgent: "bg-ink text-card", action: "bg-tint text-accent", normal: "bg-lav-tint text-lav", done: "bg-ok-tint text-ok" }[weight];
  return (
    <span className={`grid size-8 shrink-0 place-items-center rounded-[10px] text-[17px] ${cls}`}>
      <Icon name={icon} />
    </span>
  );
}
