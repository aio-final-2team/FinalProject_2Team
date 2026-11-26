import type { Dispatch, SetStateAction } from "react";
import { consentsFor, type Consent } from "@/domain/consent";
import type { Role } from "@/domain/types";

/** 역할이 받는 동의 항목을 전부 눌렀는지 */
export const allAgreed = (list: Consent[], on: string[]) => list.length > 0 && list.every((c) => on.includes(c.id));

/**
 * 동의 항목 목록. 가입 화면과 로그인 뒤 동의 화면이 같이 쓴다.
 * 모두 동의는 별도 칸이 아닌 항목만 고르고, 별도 칸(AI 처리, 건강 정보, 얼굴 찾기)은 항목마다 직접 눌러야 한다.
 */
export function ConsentChecklist({ role, on, setOn, afterLogin = false, items }: { role: Role; on: string[]; setOn: Dispatch<SetStateAction<string[]>>; afterLogin?: boolean; items?: Consent[] }) {
  const list = items ?? consentsFor(role);
  const bulk = list.filter((c) => !c.separate);
  const separate = list.filter((c) => c.separate);
  const bulkOn = bulk.length > 0 && bulk.every((c) => on.includes(c.id));
  const toggle = (id: string) => setOn((x) => (x.includes(id) ? x.filter((i) => i !== id) : [...x, id]));
  return (
    <>
      <button type="button" aria-pressed={bulkOn} onClick={() => setOn((x) => (bulkOn ? x.filter((id) => !bulk.some((c) => c.id === id)) : [...new Set([...x, ...bulk.map((c) => c.id)])]))} className={`mt-4 flex h-12 w-full items-center gap-3 rounded-lg px-3 text-left font-semibold ${bulkOn ? "bg-tint text-accent-ink" : "bg-card shadow-card"}`}>
        <Check on={bulkOn} />모두 동의합니다
      </button>
      <Cards items={bulk} on={on} toggle={toggle} afterLogin={afterLogin} />
      {separate.length > 0 && (
        <section aria-label="직접 선택해야 하는 항목" className="mt-6">
          <h2 className="px-1 text-footnote font-semibold text-ink2">직접 선택해야 하는 항목</h2>
          <p className="mt-0.5 px-1 text-caption text-ink2">위의 “모두 동의합니다”로 선택되지 않습니다. 하나씩 직접 눌러 주십시오.</p>
          <Cards items={separate} on={on} toggle={toggle} afterLogin={afterLogin} />
        </section>
      )}
      <p className="mt-3 px-1 text-caption text-ink2">동의를 거두려면 탈퇴해야 합니다. 탈퇴하면 올린 글, 사진, 얼굴 특징정보를 지웁니다.</p>
    </>
  );
}

function Check({ on }: { on: boolean }) {
  return (
    <span aria-hidden className={`grid size-5 shrink-0 place-items-center rounded-full border-2 ${on ? "border-accent bg-accent text-on-accent" : "border-line"}`}>
      {on && <svg viewBox="0 0 24 24" className="size-3" fill="none" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12.5l4.5 4.5L19 7.5" /></svg>}
    </span>
  );
}

function Cards({ items, on, toggle, afterLogin }: { items: Consent[]; on: string[]; toggle: (id: string) => void; afterLogin: boolean }) {
  return (
    <ul className="mt-3 grid gap-2">
      {items.map((c) => (
        <li key={c.id} className="rounded-lg bg-card p-3 shadow-card">
          <button type="button" aria-pressed={on.includes(c.id)} onClick={() => toggle(c.id)} className="flex w-full items-center gap-3 text-left">
            <Check on={on.includes(c.id)} />
            <b className="min-w-0 flex-1 text-callout">{c.title}</b>
            <span className="shrink-0 rounded-full bg-fill px-2 py-0.5 text-caption font-semibold text-ink2">필수{c.separate ? " · 직접 선택" : ""}</span>
          </button>
          <p className="mt-1.5 break-keep pl-8 text-footnote text-ink2">{c.summary}</p>
          <p className="mt-1 pl-8 text-caption text-ink2">동의하지 않으면 {afterLogin ? c.refuse.replace("가입할 수 없습니다", "이용할 수 없습니다") : c.refuse}.</p>
        </li>
      ))}
    </ul>
  );
}
