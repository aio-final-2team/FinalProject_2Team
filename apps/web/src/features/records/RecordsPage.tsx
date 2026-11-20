import { useState } from "react";
import { useChildren } from "@/api/notes";
import { useSession } from "@/app/session";
import { SymbolMark } from "@/components/Brand";
import { Icon } from "@/components/Icon";
import { dateLabel, todayKST } from "@/domain/notes";
import { RecordSheet } from "./RecordSheet";
import { useRecords } from "./store";

/**
 * A-01 오늘 기록 (화면별 목업). 아이 칸을 누르면 A-02 한 줄 기록 시트.
 * [API 없음] 하루 중 기록 저장 API가 아직 없어서 이 기기 브라우저에 저장한다 (store.ts).
 */
export function RecordsPage() {
  const { user } = useSession();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const kids = useChildren(cid);
  const { records, add } = useRecords(cid, date);
  const [open, setOpen] = useState<string | null>(null);
  const missing = (kids.data ?? []).filter((k) => !records[k.id]?.length);
  const openKid = kids.data?.find((k) => k.id === open);

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-32 lg:pb-10">
      <header className="flex min-h-[52px] items-center justify-between pt-2">
        <SymbolMark className="size-8" />
        <button className="grid size-10 place-items-center rounded-md text-ink" aria-label="알림">
          <Icon name="bell" className="size-6" />
        </button>
      </header>
      <h1 className="mt-1 text-large-title font-bold tracking-[-0.025em]">오늘 기록</h1>
      <p className="mt-0.5 text-footnote font-medium text-ink2">
        {dateLabel(date)} · {user?.display_name} · 생각날 때 한 줄씩
      </p>

      {kids.data && (
        <div className="mt-4 flex gap-2.5 rounded-lg bg-tint p-3 text-callout">
          <Icon name={missing.length ? "pending" : "approve"} className="mt-0.5 size-5 shrink-0 text-accent-ink" />
          <span>
            {missing.length ? (
              <>
                아직 기록이 없는 아이 <b className="text-accent-ink">{missing.length}명</b>: {missing.map((k) => k.display_name).join(", ")}
              </>
            ) : (
              "모든 아이 기록이 있어요."
            )}
          </span>
        </div>
      )}

      <div className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-4">
        {kids.isLoading && <p className="col-span-full py-6 text-center text-callout text-ink2">아이 목록을 불러오는 중…</p>}
        {kids.data?.map((k) => {
          const r = records[k.id] ?? [];
          return (
            <button
              key={k.id}
              onClick={() => setOpen(k.id)}
              className={`grid min-h-[72px] place-items-center content-center gap-0.5 rounded-lg px-1 py-2.5 text-center transition-transform duration-100 active:scale-[.97] ${r.length ? "bg-card shadow-card" : "bg-g shadow-[inset_0_0_0_1.5px_var(--sep)]"}`}
            >
              <b className="text-callout">{k.display_name}</b>
              <small className={`text-caption font-semibold tabular-nums ${r.length ? "text-ok" : "text-accent-ink"}`}>{r.length ? `기록 ${r.length} · ${r[r.length - 1].at}` : "기록 없음"}</small>
            </button>
          );
        })}
      </div>
      <p className="mt-4 px-1 text-footnote text-ink2">기록은 알림장 초안의 재료예요. 초안을 만들 때 아이별로 모아서 자료 AI에 넘겨요.</p>
      <p className="mt-1 px-1 text-caption text-ink2">임시: 저장 API가 아직 없어 이 기기에만 저장돼요.</p>

      {openKid && <RecordSheet open name={openKid.display_name} entries={records[openKid.id] ?? []} onClose={() => setOpen(null)} onSave={(t) => add(openKid.id, t)} />}
    </div>
  );
}
