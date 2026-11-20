import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useChildren, useNotes } from "@/api/notes";
import { useSession } from "@/app/session";
import { SymbolMark } from "@/components/Brand";
import { Dock, PrimaryButton } from "@/components/Dock";
import { Icon } from "@/components/Icon";
import { CHECK_KIND, dateLabel, todayKST, type CheckKind } from "@/domain/notes";
import { RecordSheet } from "@/features/records/RecordSheet";
import { useRecords } from "@/features/records/store";

type Doc = { id: string; title: string; doc_type: string; status: string; effective_from: string };

/**
 * 선생님 홈 (화면별 목업 H-01~04).
 * 하루 흐름에 따라 같은 자리의 '오늘 알림장' 카드가 바뀐다:
 * 오전(기록 수만) → 오후(기록 없는 아이 칩 + 초안 만들기) → 하원 전(걸린 아이 수) → 보낸 뒤.
 */
export function TeacherHome() {
  const { user } = useSession();
  const nav = useNavigate();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const kids = useChildren(cid);
  const notes = useNotes(cid, date);
  const { records, add } = useRecords(cid, date);
  const docs = useQuery({ queryKey: ["documents"], queryFn: () => api<{ items: Doc[] }>("/api/v1/documents?size=50").then((r) => r.items) });
  const [sheetFor, setSheetFor] = useState<string | null>(null);

  const list = notes.data ?? [];
  const total = kids.data?.length ?? 0;
  const recorded = (kids.data ?? []).filter((k) => records[k.id]?.length).length;
  const missing = (kids.data ?? []).filter((k) => !records[k.id]?.length);
  const c = { needs_check: 0, draft: 0, ready: 0, sent: 0 };
  list.forEach((n) => c[n.status]++);
  const kinds = list.flatMap((n) => n.open_checks.map((o) => o.kind));
  const kindCount = Object.entries(kinds.reduce<Record<string, number>>((a, k) => ({ ...a, [k]: (a[k] ?? 0) + 1 }), {}));
  const morning = new Date().getHours() < 13;
  const stage = !list.length ? (morning ? "morning" : "afternoon") : c.sent === list.length ? "sent" : "review";
  const meal = list[0]?.content.items.find((i) => i.key === "meal");
  const menuDoc = docs.data?.find((d) => d.doc_type === "menu" && d.status === "active");
  const notices = docs.data?.filter((d) => d.doc_type === "notice" && d.status === "active") ?? [];
  const sheetKid = kids.data?.find((k) => k.id === sheetFor);

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-48 lg:pb-10">
      {/* 머리: 마크 + 알림 벨 (목업 apphead) */}
      <header className="flex min-h-[52px] items-center justify-between pt-2">
        <SymbolMark className="size-8" />
        <button className="grid size-10 place-items-center rounded-md text-ink" aria-label="알림">
          <Icon name="bell" className="size-6" />
        </button>
      </header>
      <h1 className="mt-1 text-large-title font-bold tracking-[-0.025em]">오늘</h1>
      <p className="mt-0.5 text-footnote font-medium text-ink2">
        {dateLabel(date)} · {user?.display_name}
        {total ? ` · ${total}명` : ""}
      </p>

      <Label left={stage === "sent" ? "오늘 알림장" : "오늘 알림장 · 17:00까지"} />
      {notes.isError ? (
        <Card>
          <p className="text-callout text-danger">알림장을 불러오지 못했어요. 모의 API 서버(8000)가 켜져 있는지 확인해 주세요.</p>
        </Card>
      ) : stage === "morning" || stage === "afternoon" ? (
        <Card>
          <Big n={recorded} unit={`/${total}명 기록`} />
          <Meter parts={[[recorded, "bg-mint"]]} total={total} />
          {stage === "morning" || !missing.length ? (
            <p className="mt-2 text-footnote text-ink2">{missing.length ? "수업 중에는 알림 없이 모아 둬요. 생각날 때 한 줄씩 남겨 주세요." : "모든 아이 기록이 있어요. 하원 전에 초안을 만들어 주세요."}</p>
          ) : (
            <>
              <p className="mt-2 text-footnote">
                <b>아직 기록이 없는 아이 {missing.length}명</b> <span className="text-ink2">· 눌러서 바로 한 줄</span>
              </p>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {missing.map((k) => (
                  <button key={k.id} onClick={() => setSheetFor(k.id)} className="inline-flex h-8 items-center rounded-full bg-card px-3 text-footnote font-bold text-accent-ink shadow-[inset_0_0_0_1px_var(--accent)]">
                    + {k.display_name}
                  </button>
                ))}
              </div>
            </>
          )}
        </Card>
      ) : stage === "review" ? (
        <Card ai>
          <span className="text-caption font-bold text-accent-ink">초안 {list.length}개 준비됨 · 검사 끝</span>
          {c.needs_check ? <Big n={c.needs_check} unit="명만 확인하면 돼요" /> : c.draft ? <Big n={c.draft} unit="명 한 번에 확인하면 돼요" /> : <Big n={list.length} unit="명 모두 확인했어요" />}
          <Meter parts={[[c.ready, "bg-lav"], [c.needs_check, "bg-accent"], [c.draft, "bg-ink3"]]} total={list.length} />
          <div className="flex flex-wrap gap-x-3 text-caption font-bold text-ink2">
            <span>확인 필요 {c.needs_check}</span>
            <span>검사 통과 {c.draft}</span>
            <span>확인함 {c.ready}</span>
          </div>
          {kindCount.length > 0 && <p className="mt-2 text-footnote text-ink2">{kindCount.map(([k, n]) => `${CHECK_KIND[k as CheckKind]?.short ?? k} ${n}`).join(" · ")}</p>}
        </Card>
      ) : (
        <Card>
          <span className="text-caption font-bold text-ok">보냄</span>
          <Big n={c.sent} unit={`/${list.length}가정에 보냈어요`} />
          <Meter parts={[[c.sent, "bg-ok"]]} total={list.length} />
        </Card>
      )}

      {stage === "sent" && (
        <>
          <Label left="오늘 할 일" />
          <div className="flex items-center gap-3 rounded-lg bg-card p-3 shadow-card">
            <span className="grid size-8 place-items-center rounded-sm bg-fill">
              <Icon name="check" className="size-4" />
            </span>
            <span className="min-w-0 flex-1">
              <b className="block text-callout">오늘 알림장을 끝냈어요</b>
              <span className="text-caption text-ink2">퇴근 뒤 알림은 아이 안전 긴급만 와요</span>
            </span>
            <span className="text-caption font-bold text-ok">완료</span>
          </div>
        </>
      )}

      <Label left="오늘 우리 반" />
      <div className="grid gap-2">
        <div className="rounded-lg bg-card p-3 shadow-card">
          <b className="block text-callout">{meal ? meal.value : menuDoc ? "오늘 식단은 초안을 만들 때 들어가요" : "식단표가 아직 없어요"}</b>
          <span className="text-caption text-ink2">{meal?.source.document_title ?? menuDoc?.title ?? "원 자료"} · 알림장 식사 줄에 들어가요</span>
        </div>
        {notices.slice(0, 1).map((d) => (
          <div key={d.id} className="rounded-lg bg-card p-3 shadow-card">
            <b className="block text-callout">{d.title}</b>
            <span className="text-caption text-ink2">원 자료 · {d.effective_from}부터</span>
          </div>
        ))}
      </div>

      {stage === "afternoon" && (
        <Dock>
          <PrimaryButton onClick={() => nav("/teacher/notes")}>초안 만들기 · 반 활동 입력</PrimaryButton>
        </Dock>
      )}
      {stage === "review" && (
        <Dock>
          <PrimaryButton onClick={() => nav("/teacher/notes")}>{c.needs_check ? `걸린 아이 ${c.needs_check}명 보기` : c.draft ? "한 번에 확인하러 가기" : "보내러 가기"}</PrimaryButton>
        </Dock>
      )}

      {sheetKid && <RecordSheet open name={sheetKid.display_name} entries={records[sheetKid.id] ?? []} onClose={() => setSheetFor(null)} onSave={(t) => add(sheetKid.id, t)} />}
      {stage === "morning" && (
        <p className="mt-4 text-center text-footnote text-ink2">
          <Link to="/teacher/records" className="font-semibold text-accent">
            오늘 기록 열기
          </Link>
        </p>
      )}
    </div>
  );
}

function Label({ left }: { left: string }) {
  return <div className="mb-2 mt-5 px-1 text-footnote font-semibold text-ink2">{left}</div>;
}

function Card({ children, ai }: { children: React.ReactNode; ai?: boolean }) {
  return <section className={`rounded-lg bg-card p-3 ${ai ? "border-[1.5px] border-accent" : "shadow-card"}`}>{children}</section>;
}

function Big({ n, unit }: { n: number; unit: string }) {
  return (
    <div className="mt-1 flex items-baseline gap-1.5">
      <b className="text-[30px] font-bold leading-9 tracking-[-0.03em] tabular-nums">{n}</b>
      <span className="text-callout font-semibold text-ink2">{unit}</span>
    </div>
  );
}

function Meter({ parts, total }: { parts: [number, string][]; total: number }) {
  return (
    <div className="my-2 flex h-2 gap-0.5 overflow-hidden rounded-full bg-fill2" aria-hidden>
      {parts.map(([n, cls], i) => (n ? <i key={i} className={cls} style={{ width: `${(n / Math.max(total, 1)) * 100}%` }} /> : null))}
    </div>
  );
}
