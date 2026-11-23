
import { useMemo, useState } from "react";
import { useChildren } from "@/api/notes";
import { useSession } from "@/app/session";
import { SymbolMark } from "@/components/Brand";
import { BellLink } from "@/components/BellLink";
import { Icon } from "@/components/Icon";
import { dateLabel, todayKST } from "@/domain/notes";
import { QueryState } from "@/components/QueryState";
import { RecordSheet } from "./RecordSheet";
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
  const results = query.trim() ? (kids.data ?? []).filter((k) => k.display_name.includes(query.trim())).slice(0, 6) : [];
  const openKid = kids.data?.find((k) => k.id === open);

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-32 lg:pb-10">
      <header className="flex min-h-[52px] items-center justify-between pt-2">
        <SymbolMark className="size-8" />
        <BellLink to="/teacher/notifications" />
      </header>
      <h1 className="mt-1 text-large-title font-bold tracking-[-0.025em]">아이 관찰 기록</h1>
      <p className="mt-0.5 text-footnote font-medium text-ink2">{dateLabel(date)} · 수업 중 기억해 둘 내용을 짧게 남겨 주세요</p>

      <div className="mt-4 rounded-lg bg-tint p-3">
        <b className="text-headline">오늘 {recordedKids.length}명 기록</b>
        <p className="mt-1 text-footnote text-ink2">필요한 아이만 기록해도 돼요. 보호자에게 바로 보이지 않아요.</p>
      </div>

      <label className="mt-5 grid gap-2">
        <span className="px-1 text-footnote font-semibold text-ink2">기록할 아이 찾기</span>
        <span className="relative">
          <Icon name="search" className="pointer-events-none absolute left-3 top-3.5 size-5 text-ink2" />
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="아이 이름을 입력하세요" className="h-12 w-full rounded-md border-[1.5px] border-line bg-card pl-10 pr-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
        </span>
      </label>

      {(kids.isLoading || (kids.isError && kids.data === undefined)) && <QueryState queries={[kids]} skeleton={2} errorTitle="아이 목록을 불러오지 못했어요">{null}</QueryState>}
      {query.trim() && (
        <ul className="mt-2 overflow-hidden rounded-lg bg-card shadow-card">
          {results.map((k) => {
            const count = records[k.id]?.length ?? 0;
            return (
              <li key={k.id} className="flex min-h-14 items-center gap-3 px-3 [&+&]:border-t [&+&]:border-sep">
                <span className="grid size-8 place-items-center rounded-sm bg-fill text-footnote font-bold">{k.display_name.slice(-1)}</span>
                <span className="min-w-0 flex-1"><b className="block text-callout">{k.display_name}</b><small className="text-caption text-ink2">{count ? `오늘 기록 ${count}개` : "아직 기록 없음"}</small></span>
                <button onClick={() => { setOpen(k.id); setQuery(""); }} className="inline-flex h-9 items-center rounded-md bg-tint px-3 text-footnote font-semibold text-accent-ink">+ 기록</button>
              </li>
            );
          })}
          {!results.length && <li className="p-4 text-center text-callout text-ink2">이름과 일치하는 아이가 없어요</li>}
        </ul>
      )}

      {recordedKids.length > 0 && (
        <section className="mt-5">
          <div className="mb-2 px-1 text-footnote font-semibold text-ink2">최근 기록한 아이</div>
          <div className="flex flex-wrap gap-2">
            {recordedKids.slice(-5).reverse().map((k) => (
              <button key={k.id} onClick={() => setOpen(k.id)} className="inline-flex min-h-10 items-center gap-2 rounded-full bg-card px-3 text-footnote font-semibold shadow-card">
                {k.display_name}<span className="text-ok">{records[k.id].length}</span>
              </button>
            ))}
          </div>
        </section>
      )}

      <p className="mt-6 px-1 text-footnote text-ink2">관찰 기록은 알림장 초안을 만들 때 아이별 내용으로 반영돼요.</p>
      <p className="mt-1 px-1 text-caption text-ink2">임시 저장 · 기록 API가 연결되기 전까지 이 기기에만 보관돼요.</p>

      {openKid && <RecordSheet open name={openKid.display_name} entries={records[openKid.id] ?? []} onClose={() => setOpen(null)} onSave={(t) => add(openKid.id, t)} onRemove={(i) => remove(openKid.id, i)} />}
    </div>
  );
}
