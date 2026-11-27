
import { useMemo, useRef, useState } from "react";
import { useChildren } from "@/api/notes";
import { useSession } from "@/app/session";
import { ScreenTop } from "@/components/ScreenTop";
import { Icon } from "@/components/Icon";
import { dateLabel, todayKST } from "@/domain/notes";
import { QueryState } from "@/components/QueryState";
import { ChildAvatar } from "@/components/ChildAvatar";
import { RecordSheet } from "./RecordSheet";
import { useNotebook } from "@/features/notes/notebookCtx";
import { useRecords } from "./store";

/** 아이를 전부 펼치지 않고 검색·선택한 뒤 짧게 기록한다. 서버 API 전까지 이 기기에 임시 저장한다. */
export function RecordsPage() {
  const { user } = useSession();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const kids = useChildren(cid);
  const { records, add, remove } = useRecords(cid, date);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string | null>(null);
  const recordedKids = useMemo(() => (kids.data ?? []).filter((k) => records[k.id]?.length), [kids.data, records]);
  const list = query.trim() ? (kids.data ?? []).filter((k) => k.display_name.includes(query.trim())) : (kids.data ?? []);
  const openKid = kids.data?.find((k) => k.id === open);
  /* 닫는 동안에도 시트를 그대로 두어야 닫힘 애니메이션이 돌고, 그동안 뒤 화면이 눌리지 않는다 */
  const lastKid = useRef(openKid);
  if (openKid) lastKid.current = openKid;
  const shownKid = openKid ?? lastKid.current;
  const nb = useNotebook();

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-32 lg:pb-10">
      <ScreenTop title={nb?.title ?? "아이 관찰 기록"} sub={`${dateLabel(date)} · 수업 중 기억해 둘 내용을 짧게 남겨 주세요`} />
      {nb?.top}

      <div className="mt-4 rounded-lg bg-tint p-3">
        <b className="text-headline">오늘 {recordedKids.length}명 기록</b>
        <p className="mt-1 text-footnote text-ink2">필요한 아이만 기록해도 돼요. 보호자에게 바로 보이지 않아요.</p>
      </div>

      <label className="mt-5 grid gap-2">
        <span className="px-1 text-footnote font-semibold text-ink2">아이 이름으로 찾기</span>
        <span className="relative">
          <Icon name="search" className="pointer-events-none absolute left-3 top-3.5 size-5 text-ink2" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="아이 이름을 입력하세요" className="h-12 w-full rounded-md border-[1.5px] border-line bg-card pl-10 pr-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
        </span>
      </label>

      {(kids.isLoading || (kids.isError && kids.data === undefined)) && <QueryState queries={[kids]} skeleton={2} errorTitle="아이 목록을 불러오지 못했어요">{null}</QueryState>}
      {kids.data && (
        <section className="mt-4" aria-label="우리 반 아이들">
          <div className="mb-2 flex items-baseline justify-between px-1">
            <h2 className="text-footnote font-semibold text-ink2">{query.trim() ? `검색 결과 ${list.length}명` : `우리 반 ${list.length}명`}</h2>
            <span className="text-caption text-ink2">아이를 누르면 기록해요</span>
          </div>
          {list.length ? (
            <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {list.map((k) => {
                const r = records[k.id] ?? [];
                return (
                  <li key={k.id}>
                    <button
                      type="button"
                      onClick={() => { setOpen(k.id); setQuery(""); }}
                      className={`flex w-full items-center gap-3 rounded-lg p-3 text-left transition-transform duration-100 active:scale-[.97] ${r.length ? "bg-card shadow-card" : "bg-g shadow-[inset_0_0_0_1.5px_var(--sep)]"}`}
                    >
                      <ChildAvatar name={k.display_name} photo={k.profile_photo} childId={k.id} size={40} tone={r.length ? "tint" : "fill"} />
                      <b className="min-w-0 flex-1 truncate text-callout">{k.display_name}</b>
                      <span aria-label={`기록 ${r.length}개`} className={`shrink-0 text-headline font-bold tabular-nums ${r.length ? "text-accent-ink" : "text-ink2/60"}`}>{r.length}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="rounded-lg bg-card p-4 text-center text-callout text-ink2 shadow-card">이름과 일치하는 아이가 없어요</p>
          )}
        </section>
      )}

      <p className="mt-6 px-1 text-footnote text-ink2">관찰 기록은 알림장 초안을 만들 때 아이별 내용으로 반영돼요.</p>
      <p className="mt-1 px-1 text-caption text-ink2">임시 저장이에요. 이 기기에만 보관돼요.</p>

      {shownKid && <RecordSheet key={shownKid.id} open={!!openKid} name={shownKid.display_name} entries={records[shownKid.id] ?? []} onClose={() => setOpen(null)} onSave={(t) => add(shownKid.id, t)} onRemove={(i) => remove(shownKid.id, i)} />}
    </div>
  );
}
