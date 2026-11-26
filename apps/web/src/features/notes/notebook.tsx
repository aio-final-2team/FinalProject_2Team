import { useEffect } from "react";
import { useSearchParams } from "react-router";
import { NotebookCtx } from "./notebookCtx";
import { NotesPage } from "./NotesPage";
import { RecordsPage } from "@/features/records/RecordsPage";

/**
 * 교사 알림장 탭. 관찰 기록(재료)과 알림장(결과)은 한 흐름이라 한 탭 안에서 두 칸으로 나눈다.
 * 두 화면은 제목을 "알림장"으로 맞추고, 칸 전환 줄을 제목 아래에 붙인다.
 */
const TABS = [
  { key: "notes", label: "오늘 알림장" },
  { key: "records", label: "관찰 기록" },
] as const;

export function NotebookPage() {
  const [params, setParams] = useSearchParams();
  /* 주소에 칸이 없으면(아래 탭으로 돌아올 때) 마지막으로 본 칸을 보여 준다 */
  let last = "notes";
  try { last = sessionStorage.getItem("yuchion.notebookTab") ?? "notes"; } catch { /* 무시 */ }
  const asked = params.get("tab");
  const tab = (asked === "records" || asked === "notes" ? asked : last) === "records" ? "records" : "notes";
  useEffect(() => { try { sessionStorage.setItem("yuchion.notebookTab", tab); } catch { /* 무시 */ } }, [tab]);
  const top = (
    <div role="tablist" aria-label="알림장 구성" className="mt-4 grid grid-flow-col gap-1 rounded-md bg-fill p-1">
      {TABS.map((t) => (
        <button key={t.key} role="tab" aria-selected={tab === t.key} onClick={() => { try { sessionStorage.setItem("yuchion.notebookTab", t.key); } catch { /* 무시 */ } setParams({ tab: t.key }, { replace: true }); }} className={`h-9 rounded-sm text-footnote font-semibold ${tab === t.key ? "bg-card text-ink shadow-card" : "text-ink2"}`}>
          {t.label}
        </button>
      ))}
    </div>
  );
  return <NotebookCtx.Provider value={{ title: "알림장", top }}>{tab === "records" ? <RecordsPage /> : <NotesPage />}</NotebookCtx.Provider>;
}
