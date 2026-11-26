import { useMemo, useState } from "react";
import { useClassroomConsents } from "@/api/consents";
import { useAllCards } from "@/api/cards";
import { useSession } from "@/app/session";
import { ChildAvatar } from "@/components/ChildAvatar";
import { QueryState } from "@/components/QueryState";
import { ScreenTop } from "@/components/ScreenTop";
import { StateView } from "@/components/StateView";
import { Pill } from "@/components/Tags";
import type { Role } from "@/domain/types";

/**
 * 반 아이별 보호자 동의 현황 (API 55). 담임은 우리 반, 원장은 반을 골라서 본다.
 * 원장 계정은 반 목록 API가 없어서, 카드 목록이 주는 반으로 고른다.
 */
export function ClassConsentsPage({ role }: { role: Exclude<Role, "parent"> }) {
  const { user } = useSession();
  const cards = useAllCards();
  const classes = useMemo(() => {
    const m = new Map<string, string>();
    for (const c of cards) if (c.classroomId) m.set(c.classroomId, c.className);
    return [...m].map(([id, name]) => ({ id, name }));
  }, [cards]);
  const choices = role === "teacher" ? (user?.classroom_ids ?? []).map((id) => ({ id, name: classes.find((c) => c.id === id)?.name ?? "우리 반" })) : classes;
  const [picked, setPicked] = useState<string>();
  const current = choices.find((c) => c.id === picked) ?? choices[0];
  const q = useClassroomConsents(current?.id);
  const [only, setOnly] = useState(false);

  const items = q.data ?? [];
  const waiting = items.filter((i) => !i.complete);
  const rows = (only ? waiting : items).slice().sort((a, b) => Number(a.complete) - Number(b.complete));
  const back = role === "teacher" ? { to: "/teacher/home", label: "홈" } : { to: "/director/overview", label: "현황" };

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop back={back} title="보호자 동의 현황" sub={q.data && current ? `${current.name} · ${items.length}명 중 ${items.length - waiting.length}명이 동의했어요` : current?.name} />
      {choices.length > 1 && (
        <div className="mt-3 flex gap-2 overflow-x-auto" role="group" aria-label="반 고르기">
          {choices.map((c) => (
            <button key={c.id} type="button" aria-pressed={c.id === current?.id} onClick={() => setPicked(c.id)} className={`h-9 shrink-0 rounded-full px-3 text-footnote font-semibold ${c.id === current?.id ? "bg-ink text-card" : "bg-card text-ink shadow-card"}`}>
              {c.name}
            </button>
          ))}
        </div>
      )}
      {!current ? (
        <div className="mt-6"><StateView kind="empty" audience="staff" title="반 정보를 찾지 못했어요" sub="잠시 뒤 다시 열어 주세요" /></div>
      ) : (
        <QueryState queries={[q]} skeleton={4} errorTitle="동의 현황을 불러오지 못했어요">
          <div className="mt-3 flex gap-2" role="group" aria-label="보기">
            {[
              { k: false, label: `전체 ${items.length}` },
              { k: true, label: `미동의 ${waiting.length}` },
            ].map((f) => (
              <button key={String(f.k)} type="button" aria-pressed={only === f.k} onClick={() => setOnly(f.k)} className={`h-9 rounded-full px-3 text-footnote font-semibold ${only === f.k ? "bg-ink text-card" : "bg-card text-ink shadow-card"}`}>
                {f.label}
              </button>
            ))}
          </div>
          {rows.length === 0 ? (
            <div className="mt-6"><StateView kind="empty" audience="staff" title="모든 보호자가 동의했어요" sub="미동의 아이가 없어요" /></div>
          ) : (
            <ul className="mt-3 overflow-hidden rounded-lg bg-card shadow-card [&>li+li]:border-t [&>li+li]:border-sep">
              {rows.map((c) => (
                <li key={c.child_id} className="flex items-center gap-3 px-3 py-2.5">
                  <ChildAvatar name={c.display_name} childId={c.child_id} />
                  <span className="min-w-0 flex-1">
                    <b className="block truncate text-callout font-semibold">{c.display_name}</b>
                    <span className="text-footnote text-ink2">{c.guardians_total ? `보호자 ${c.guardians_total}명 중 ${c.guardians_complete}명 동의` : "연결된 보호자가 없어요"}</span>
                  </span>
                  <Pill tone={c.complete ? "done" : "wait"}>{c.complete ? "동의 완료" : "동의 전"}</Pill>
                </li>
              ))}
            </ul>
          )}
        </QueryState>
      )}
    </div>
  );
}
