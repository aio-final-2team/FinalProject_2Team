import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { useChildren, useCreateDraft, useDraftJob, useNotes, usePatchNote, useSendNotes } from "@/api/notes";
import { useSession } from "@/app/session";
import { Dock, PrimaryButton, SubButton } from "@/components/Dock";
import { Icon } from "@/components/Icon";
import { Sheet } from "@/components/Sheet";
import { useToast } from "@/components/Toast";
import { CHECK_KIND, NOTE_STATUS, dateLabel, nameI, todayKST, type DailyNote, type NoteStatus } from "@/domain/notes";

/**
 * 오늘 알림장 (FR-10, API 22~26, v0.4).
 * 초안이 없으면 입력 화면, 만드는 중이면 진행 화면, 있으면 아이별 목록과 한 번에 보내기.
 */
export function NotesPage() {
  const { user } = useSession();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const notes = useNotes(cid, date);
  const [jobId, setJobId] = useState<string>();

  if (notes.isLoading) return <Shell date={date}><p className="py-10 text-center text-callout text-ink2">불러오는 중…</p></Shell>;
  if (notes.isError)
    return (
      <Shell date={date}>
        <p className="rounded-lg bg-danger-tint p-4 text-callout text-danger">알림장을 불러오지 못했어요. 모의 API 서버(8000)가 켜져 있는지 확인해 주세요.</p>
      </Shell>
    );
  if (jobId) return <Progress jobId={jobId} date={date} onDone={() => setJobId(undefined)} />;
  if (!notes.data?.length) return <Compose date={date} onStarted={setJobId} />;
  return <Review notes={notes.data} date={date} />;
}

function Shell({ date, sub, children }: { date: string; sub?: string; children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-[680px] px-4 pb-48 pt-6 lg:pb-10 lg:pt-10">
      <h1 className="text-large-title font-bold tracking-[-0.025em]">오늘 알림장</h1>
      <p className="mb-4 mt-0.5 text-footnote font-medium text-ink2">{sub ?? `${dateLabel(date)} · 17:00까지`}</p>
      {children}
    </div>
  );
}

/* ── 입력: 반 활동·준비물 + 아이별 메모 ── */
function Compose({ date, onStarted }: { date: string; onStarted: (id: string) => void }) {
  const { user } = useSession();
  const cid = user!.classroom_ids[0];
  const kids = useChildren(cid);
  const create = useCreateDraft();
  const [activities, setActivities] = useState("");
  const [supplies, setSupplies] = useState("");
  const [memos, setMemos] = useState<Record<string, string>>({});
  const [err, setErr] = useState("");
  const filled = Object.values(memos).filter((m) => m.trim()).length;
  const total = kids.data?.length ?? 0;

  const submit = () => {
    if (!activities.trim()) {
      setErr("오늘 반 활동을 한 줄 이상 적어 주세요. 모든 아이 초안의 첫 문장이 돼요.");
      document.getElementById("note-activities")?.focus();
      return;
    }
    setErr("");
    const child_memos = Object.entries(memos)
      .filter(([, m]) => m.trim())
      .map(([child_id, memo]) => ({ child_id, memo: memo.trim().slice(0, 500) }));
    create.mutate(
      { classroom_id: cid, note_date: date, activities: activities.trim(), supplies: supplies.trim(), child_memos },
      {
        onSuccess: (job) => onStarted(job.input_id),
        onError: (e) => setErr(e instanceof ApiError ? e.message : "초안 만들기를 시작하지 못했어요. 잠시 뒤 다시 눌러 주세요."),
      },
    );
  };

  return (
    <Shell date={date}>
      <section className="overflow-hidden rounded-lg bg-card shadow-card">
        <label className="grid gap-1.5 p-3">
          <span className="text-footnote font-semibold">오늘 반 활동</span>
          <textarea
            id="note-activities"
            rows={2}
            value={activities}
            onChange={(e) => setActivities(e.target.value)}
            placeholder="예: 가을 낙엽으로 왕관 만들기, 놀이터에서 술래잡기"
            className={`resize-none rounded-md border-[1.5px] bg-card px-3 py-2.5 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)] ${err && !activities.trim() ? "border-danger" : "border-line"}`}
          />
        </label>
        <label className="grid gap-1.5 border-t border-sep p-3">
          <span className="text-footnote font-semibold">
            준비물 <span className="font-medium text-ink2">없으면 비워 두세요</span>
          </span>
          <input
            value={supplies}
            onChange={(e) => setSupplies(e.target.value)}
            placeholder="예: 11/27(금) 김장 체험: 앞치마, 팔토시"
            className="h-12 rounded-md border-[1.5px] border-line bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]"
          />
        </label>
      </section>
      {err && (
        <p role="alert" className="mt-2 text-footnote font-medium text-danger">
          {err}
        </p>
      )}

      <div className="mt-5 flex items-baseline justify-between px-1 text-footnote font-semibold text-ink2">
        <span>아이별 메모</span>
        <span>
          <b className="text-ink tabular-nums">{filled}</b>/{total}명
        </span>
      </div>
      <p className="mt-1 px-1 text-footnote text-ink2">짧게 적어도 돼요. 메모에 없는 말은 검사에서 걸러요. 비워 두면 반 활동만 들어가요.</p>
      <section className="mt-2 overflow-hidden rounded-lg bg-card shadow-card">
        {kids.isLoading && <p className="p-4 text-callout text-ink2">아이 목록을 불러오는 중…</p>}
        {kids.data?.map((k, i) => (
          <label key={k.id} className={`flex items-center gap-3 px-3 py-2 ${i ? "border-t border-sep" : ""}`}>
            <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-sm bg-fill text-footnote font-bold">
              {k.display_name.slice(-1)}
            </span>
            <span className="w-12 shrink-0 text-callout font-semibold">{k.display_name}</span>
            <input
              value={memos[k.id] ?? ""}
              onChange={(e) => setMemos((m) => ({ ...m, [k.id]: e.target.value }))}
              maxLength={500}
              placeholder="예: 점심 반 남김, 블록놀이 집중"
              aria-label={`${k.display_name} 메모`}
              className="h-10 min-w-0 flex-1 rounded-md border border-line bg-card px-2.5 text-callout outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]"
            />
          </label>
        ))}
      </section>

      <Dock>
        <PrimaryButton onClick={submit} loading={create.isPending}>
          초안 만들기
        </PrimaryButton>
      </Dock>
    </Shell>
  );
}

/* ── 진행: 202 뒤 상태 조회 ── */
function Progress({ jobId, date, onDone }: { jobId: string; date: string; onDone: () => void }) {
  const { user } = useSession();
  const qc = useQueryClient();
  const job = useDraftJob(jobId);
  const st = job.data?.draft_status ?? "queued";
  const step = st === "queued" ? 0 : st === "running" ? 1 : 3;
  useEffect(() => {
    if (st === "succeeded") qc.invalidateQueries({ queryKey: ["notes", user?.classroom_ids[0], date] }).then(onDone);
  }, [st, qc, user, date, onDone]);
  const rows: [string, string, string][] = [
    ["서버", "접수됐어요", "queued"],
    ["자료 AI", "아이별 초안을 쓰는 중", "반 활동 + 메모 + 식단표"],
    ["검사 AI", "메모·자료와 대조하는 중", "없는 말, 다른 아이, 날짜"],
  ];
  return (
    <Shell date={date} sub="초안을 만들고 있어요">
      {st === "failed" ? (
        <div className="grid gap-3 rounded-lg bg-card p-4 shadow-card">
          <b className="text-headline">초안을 만들지 못했어요</b>
          <p className="text-callout text-ink2">{job.data?.error?.message ?? "잠시 뒤 다시 만들어 주세요."} 입력한 내용은 저장돼 있어요.</p>
          <SubButton onClick={onDone}>다시 시도</SubButton>
        </div>
      ) : (
        <ol className="grid gap-3 rounded-lg bg-card p-4 shadow-card">
          {rows.map(([who, t, d], i) => (
            <li key={t} className="grid grid-cols-[16px_1fr] gap-3">
              <span className={`mt-1 size-3.5 rounded-full border-2 ${i < step ? "border-accent bg-accent" : i === step ? "border-accent shadow-[0_0_0_3px_var(--tint)]" : "border-fill2"}`} />
              <span>
                <span className="block text-caption font-bold text-lav">{who}</span>
                <span className="block text-callout font-semibold">{t}</span>
                <span className="block text-caption text-ink2">{d}</span>
              </span>
            </li>
          ))}
        </ol>
      )}
      <Dock>
        <PrimaryButton disabled loading={st !== "failed"}>
          만드는 중
        </PrimaryButton>
      </Dock>
    </Shell>
  );
}

/* ── 목록: 걸린 아이 먼저, 통과한 아이는 한 번에 확인, 모두 확인되면 한 번에 보내기 ── */
const TABS: [NoteStatus, string][] = [
  ["needs_check", "확인 필요"],
  ["draft", "검사 통과"],
  ["ready", "확인함"],
  ["sent", "보냄"],
];

function Review({ notes, date }: { notes: DailyNote[]; date: string }) {
  const { user } = useSession();
  const cid = user!.classroom_ids[0];
  const kids = useChildren(cid);
  const names = useMemo(() => Object.fromEntries((kids.data ?? []).map((k) => [k.id, k.display_name])), [kids.data]);
  const patch = usePatchNote(cid, date);
  const send = useSendNotes(cid, date);
  const toast = useToast();
  const [sheet, setSheet] = useState(false);
  const [busy, setBusy] = useState(false);
  const count = { needs_check: 0, draft: 0, ready: 0, sent: 0 } as Record<NoteStatus, number>;
  notes.forEach((n) => count[n.status]++);
  const allSent = count.sent === notes.length;
  const [tab, setTab] = useState<NoteStatus>(count.needs_check ? "needs_check" : count.draft ? "draft" : allSent ? "sent" : "ready");
  const list = notes.filter((n) => n.status === tab);
  const notReady = notes.filter((n) => n.status === "needs_check" || n.status === "draft").length;

  /* 한꺼번에 확인하는 API가 없어서 아이마다 PATCH를 차례로 부른다 */
  const confirmClean = async () => {
    setBusy(true);
    const targets = notes.filter((n) => n.status === "draft");
    let ok = 0;
    for (const n of targets) {
      try {
        await patch.mutateAsync({ id: n.id, body: { confirm: true } });
        ok++;
      } catch {
        /* 실패한 아이는 목록에 남는다 */
      }
    }
    setBusy(false);
    toast({ kind: "ok", title: `${ok}명 알림장을 확인했어요`, sub: ok < targets.length ? `${targets.length - ok}명은 다시 눌러 주세요` : undefined });
  };

  const doSend = () =>
    send.mutate(undefined, {
      onSuccess: (r) => {
        setSheet(false);
        setTab("sent");
        toast({ kind: "ok", title: `${r.sent_count}가정에 알림장을 보냈어요`, sub: "학부모 홈 '오늘 알림장'에 올라갔어요" });
      },
      onError: (e) => {
        setSheet(false);
        const blocked = e instanceof ApiError && e.code === "NOTE_BATCH_BLOCKED";
        toast({ kind: "error", title: blocked ? "확인이 안 끝난 알림장이 있어요" : "보내지 못했어요", sub: blocked ? "확인 필요 탭을 봐 주세요" : "잠시 뒤 다시 보내 주세요" });
      },
    });

  const preview = notes[0];
  return (
    <Shell date={date} sub={`${dateLabel(date)} · ${notes.length}명 · ${allSent ? "보냄" : "17:00까지"}`}>
      <div role="tablist" className="mb-3 flex gap-5 overflow-x-auto border-b border-sep">
        {TABS.filter(([s]) => s !== "sent" || count.sent).map(([s, label]) => (
          <button
            key={s}
            role="tab"
            aria-selected={tab === s}
            onClick={() => setTab(s)}
            className={`-mb-px whitespace-nowrap border-b-2 py-2.5 text-callout font-semibold ${tab === s ? "border-accent text-ink" : "border-transparent text-ink2"}`}
          >
            {label}
            <small className="ml-1 text-caption font-bold text-accent tabular-nums">{count[s]}</small>
          </button>
        ))}
      </div>

      {tab === "needs_check" && count.needs_check > 0 && (
        <div className="mb-3 flex gap-2.5 rounded-lg bg-tint p-3 text-callout">
          <Icon name="ai" className="mt-0.5 size-5 shrink-0 text-accent-ink" />
          <span>
            검사 AI가 <b className="text-accent-ink">{count.needs_check}명</b>에게서 확인할 곳을 찾았어요. 아이를 눌러 고치거나 그대로 둘지 정해 주세요.
          </span>
        </div>
      )}
      {tab === "draft" && count.draft > 0 && (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2 rounded-lg bg-tint p-3 text-callout">
          <span>확인할 곳이 없는 아이예요. 다 읽었으면 한 번에 확인하세요.</span>
          <SubButton onClick={confirmClean} disabled={busy} className="bg-card">
            {busy ? "확인하는 중…" : `${count.draft}명 한 번에 확인`}
          </SubButton>
        </div>
      )}

      {list.length ? (
        <ul className="overflow-hidden rounded-lg bg-card shadow-card">
          {list.map((n, i) => {
            const childLine = n.content.items.find((it) => it.key === "child")?.value;
            const firstCheck = n.open_checks[0];
            const sub = n.status === "needs_check" && firstCheck ? CHECK_KIND[firstCheck.kind]?.title ?? firstCheck.problem : childLine ?? "반 활동만 들어갔어요";
            return (
              <li key={n.id} className={i ? "border-t border-sep" : ""}>
                <Link to={`/teacher/notes/${n.id}`} className="flex min-h-14 items-center gap-3 px-3 py-2">
                  <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-sm bg-fill text-footnote font-bold">
                    {(names[n.child_id] ?? "?").slice(-1)}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline gap-2">
                      <b className="text-headline font-semibold">{names[n.child_id] ?? "아이"}</b>
                      <span className={`text-caption font-bold ${NOTE_STATUS[n.status].cls}`}>{NOTE_STATUS[n.status].label}</span>
                    </span>
                    <span className={`block truncate text-footnote ${childLine || n.status === "needs_check" ? "text-ink2" : "text-ink3"}`}>{sub}</span>
                  </span>
                  <Icon name="chevR" className="size-4 text-ink3" />
                </Link>
              </li>
            );
          })}
        </ul>
      ) : (
        <p className="py-10 text-center text-callout text-ink2">여기에 해당하는 아이가 없어요</p>
      )}

      {!allSent && (
        <Dock reason={notReady ? `아직 확인 안 한 알림장 ${notReady}개 · 모두 확인해야 보낼 수 있어요` : `${notes.length}명 모두 확인했어요`} reasonIcon={notReady ? "lock" : "check"}>
          <PrimaryButton disabled={!!notReady} onClick={() => setSheet(true)}>
            {notes.length}명에게 한 번에 보내기
          </PrimaryButton>
        </Dock>
      )}

      <Sheet open={sheet} onClose={() => setSheet(false)} title={`${notes.length}명에게 한 번에 보내기`}>
        <p className="text-footnote text-ink2">받는 사람: 우리 반 보호자 · 보내면 고칠 수 없어요</p>
        {preview && (
          <div className="grid gap-1 rounded-lg bg-g p-3 text-callout">
            <b className="text-headline">{nameI(names[preview.child_id] ?? "아이")}의 오늘</b>
            {preview.content.items.map((it, i) => (
              <span key={i}>
                <b className="mr-1.5 text-footnote text-ink2">{it.label}</b>
                {it.value}
              </span>
            ))}
          </div>
        )}
        <div className="grid grid-cols-[1fr_2fr] gap-2">
          <SubButton tone="gray" className="h-[52px]" onClick={() => setSheet(false)}>
            취소
          </SubButton>
          <PrimaryButton onClick={doSend} loading={send.isPending}>
            보내기
          </PrimaryButton>
        </div>
      </Sheet>
    </Shell>
  );
}
