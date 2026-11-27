import { ScreenTop } from "@/components/ScreenTop";
import { useNotebook } from "./notebookCtx";
import { ChildAvatar } from "@/components/ChildAvatar";
import { clearCompose, loadCompose, saveCompose } from "./composeDraft";
import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { QueryState } from "@/components/QueryState";
import { loadInputId, saveInputId, useChildren, useCreateDraft, useDraftJob, useNotes, usePatchNote, useRegenerate, useResetNotes, useSendNotes } from "@/api/notes";
import { useSession } from "@/app/session";
import { Button } from "@/components/Button";
import { Dock, PrimaryButton, SubButton } from "@/components/Dock";
import { Icon } from "@/components/Icon";
import { Sheet } from "@/components/Sheet";
import { useToast } from "@/components/Toast";
import { useAllCards } from "@/api/cards";
import { CHECK_KIND, COMMON_KEYS, NOTE_STATUS, dateLabel, itemLabel, nameI, noMd, todayKST, type DailyNote, type NoteItem } from "@/domain/notes";
import { RecordSheet } from "@/features/records/RecordSheet";
import { useRecords } from "@/features/records/store";

/**
 * 오늘 알림장 (화면별 목업 A-03 · A-04 · A-05 · A-07).
 * 초안이 없으면 반 활동 입력, 만드는 중이면 에이전트 단계, 있으면 '걸린 아이만' 묶음 화면.
 */
export function NotesPage() {
  const { user } = useSession();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const notes = useNotes(cid, date);
  const [jobId, setJobId] = useState<string>();
  /* 알림장이 아직 없는데 이 기기에 접수한 작업이 있으면 그 진행 상태를 이어서 본다 (API 23). 새로고침해도 입력을 다시 쓰지 않는다 */
  const stored = !notes.data?.length ? loadInputId(cid, date) : null;
  const resume = useDraftJob(stored ?? undefined);
  /* QA 초기화가 끝나면 보던 진행 화면을 닫고 처음 화면(활동 입력)으로 돌아간다 */
  useEffect(() => {
    const h = () => setJobId(undefined);
    window.addEventListener("yuchion:notes-reset", h);
    return () => window.removeEventListener("yuchion:notes-reset", h);
  }, []);

  if (notes.isLoading || (notes.isError && notes.data === undefined))
    return (
      <Frame>
        <QueryState queries={[notes]} errorTitle="알림장을 불러오지 못했어요">{null}</QueryState>
      </Frame>
    );
  if (jobId) return <Progress jobId={jobId} onDone={() => setJobId(undefined)} />;
  if (!notes.data?.length) {
    if (stored && resume.data && resume.data.draft_status !== "succeeded") return <Progress jobId={stored} onDone={() => setJobId(undefined)} />;
    return <Compose onStarted={setJobId} />;
  }
  return <Review notes={notes.data} />;
}

/* 공통 틀: ‹ 홈, 큰 제목, 보조 줄 */
function Frame({ title = "오늘 알림장", sub, children }: { title?: string; sub?: React.ReactNode; children: React.ReactNode }) {
  const { user } = useSession();
  const nb = useNotebook();
  return (
    <div className="mx-auto max-w-[680px] px-4 pb-48 lg:pb-10">
      <ScreenTop title={nb?.title ?? title} sub={sub ?? `${user?.display_name} · ${dateLabel(todayKST())} · 17:00까지`} />
      {nb?.top}
      {children}
      {QA_TOOLS && <QaReset />}
    </div>
  );
}

/** 시연 계정이 켜진 빌드(QA·시연 서버)에서만 보인다. 최종 제출본(VITE_DEMO_ACCOUNTS=false)에서는 나오지 않는다 */
const QA_TOOLS = import.meta.env.VITE_DEMO_ACCOUNTS !== "false";

/** QA 전용: 오늘 알림장을 모두 지우고 처음부터 다시 시험한다(API 71). 서버의 QA 도구가 꺼져 있으면 쓸 수 없다고 알려 준다 */
function QaReset() {
  const { user } = useSession();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const reset = useResetNotes(cid, date);
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const run = () =>
    reset.mutate(undefined, {
      onSuccess: (r) => {
        setOpen(false);
        toast({ kind: "ok", title: "알림장을 처음 상태로 돌렸어요", sub: `알림장 ${r.deleted.notes}개와 관련 카드 ${r.deleted.cards}개를 지웠어요` });
      },
      onError: (e) => {
        setOpen(false);
        const s = e instanceof ApiError ? e.status : 0;
        toast({ kind: "error", title: s === 404 ? "이 서버에서는 쓸 수 없어요" : s === 403 ? "담임 선생님만 쓸 수 있어요" : "초기화하지 못했어요", sub: s === 404 ? "QA 서버에서만 켜져 있어요" : s ? undefined : "연결을 확인하고 다시 눌러 주세요" });
      },
    });
  return (
    <>
      <button type="button" onClick={() => setOpen(true)} className="mt-8 inline-flex h-9 items-center rounded-md px-2.5 text-footnote font-semibold text-ink2 active:scale-[.97]">알림장 다시 시험하기 (QA)</button>
      <Sheet open={open} onClose={() => setOpen(false)} title="알림장을 처음부터 다시 시험할까요?">
        <p className="text-callout text-ink">{dateLabel(date)} 알림장과 그에 딸린 카드·알림이 모두 지워져요. 이미 보낸 알림장도 포함돼요. 지운 뒤에는 되돌릴 수 없어요.</p>
        <p className="text-footnote text-ink2">시험용 서버에서만 쓸 수 있어요. 학부모 답장은 남고, 어느 알림장의 답장인지만 비워져요.</p>
        <Button variant="danger" loading={reset.isPending} onClick={run}>지우고 다시 시작</Button>
        <Button variant="plain" size="sm" onClick={() => setOpen(false)}>취소</Button>
      </Sheet>
    </>
  );
}

function Label({ children, right }: { children: React.ReactNode; right?: React.ReactNode }) {
  return (
    <div className="mb-2 mt-5 flex items-baseline justify-between px-1 text-footnote font-semibold text-ink2">
      <span>{children}</span>
      {right}
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

/* ── A-03 오늘 알림장(초안 전): 오늘 기록 현황 + 반 활동·준비물 + 자동으로 들어가는 식단 ── */
function Compose({ onStarted }: { onStarted: (id: string) => void }) {
  const { user } = useSession();
  const cid = user!.classroom_ids[0];
  const date = todayKST();
  const kids = useChildren(cid);
  const { records, memoOf } = useRecords(cid, date);
  const create = useCreateDraft();
  const saved = useMemo(() => loadCompose(cid, date), [cid, date]);
  const [activities, setActivities] = useState(saved.activities);
  const [supplies, setSupplies] = useState(saved.supplies);
  /* 적는 대로 이 기기에 임시 저장해서, 다른 화면에 다녀와도 내용이 남는다 */
  useEffect(() => { saveCompose(cid, date, { activities, supplies }); }, [cid, date, activities, supplies]);
  const [err, setErr] = useState("");
  const recorded = (kids.data ?? []).filter((k) => records[k.id]?.length);

  const submit = () => {
    if (!activities.trim()) {
      setErr("오늘 반 활동을 한 줄 이상 적어 주세요. 모든 아이 초안의 첫 문장이 돼요.");
      document.getElementById("note-activities")?.focus();
      return;
    }
    setErr("");
    create.mutate(
      {
        classroom_id: cid,
        note_date: date,
        activities: activities.trim(),
        supplies: supplies.trim(),
        child_memos: recorded.map((k) => ({ child_id: k.id, memo: memoOf(k.id) })).filter((m) => m.memo),
      },
      { onSuccess: (job) => { saveInputId(cid, date, job.input_id); clearCompose(cid, date); onStarted(job.input_id); }, onError: (e) => setErr(e instanceof ApiError ? e.message : "초안 만들기를 시작하지 못했어요. 잠시 뒤 다시 눌러 주세요.") },
    );
  };
  const field = "w-full rounded-md border-[1.5px] bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]";

  return (
    <Frame title="오늘 알림장 만들기">
      <Label>관찰 기록</Label>
      <section className="rounded-lg bg-card p-3 shadow-card">
        <div className="flex items-baseline gap-1.5">
          <b className="text-[30px] font-bold leading-9 tracking-[-0.03em] tabular-nums">{recorded.length}</b>
          <span className="text-callout font-semibold text-ink2">명 기록 반영</span>
        </div>
        <p className="text-footnote text-ink2">기록이 있는 아이의 개별 내용만 선택해서 반영돼요</p>
        <Link to="/teacher/notes?tab=records" className="mt-2 inline-flex h-8 items-center rounded-md bg-fill px-2.5 text-footnote font-semibold">
          관찰 기록 보기
        </Link>
      </section>

      <Label>오늘 함께한 활동</Label>
      <textarea
        id="note-activities"
        rows={3}
        maxLength={2000}
        value={activities}
        onChange={(e) => setActivities(e.target.value)}
       
        placeholder="예: 가을 낙엽으로 왕관 만들기, 놀이터에서 술래잡기"
        className={`${field} resize-none py-2.5 ${err && !activities.trim() ? "border-danger" : "border-line"}`}
      />
      {err && (
        <p role="alert" className="mt-1.5 text-footnote font-medium text-danger">
          {err}
        </p>
      )}
      <Label>가정에서 준비할 것</Label>
      <input value={supplies} maxLength={2000} onChange={(e) => setSupplies(e.target.value)} placeholder="예: 11/27(금) 김장 체험: 앞치마, 팔토시" className={`${field} h-12 border-line`} />
      {(activities || supplies) && <p className="mt-1.5 px-1 text-caption text-ink2">적은 내용은 이 기기에 임시 저장돼요</p>}

      <Label>
        <span className="inline-flex items-center gap-1">
          <Icon name="document" className="size-4" />
          자동으로 들어가요
        </span>
      </Label>
      <div className="flex flex-wrap gap-1.5">
        <span className="rounded-sm bg-ok-tint px-2 py-1 text-caption font-semibold text-ok">오늘 식단표</span>
        <span className="rounded-sm bg-lav-tint px-2 py-1 text-caption font-semibold text-lav">오늘 접수한 보호자 요청</span>
      </div>

      <Dock>
        <PrimaryButton onClick={submit} loading={create.isPending}>
          아이별 초안 만들기
        </PrimaryButton>
      </Dock>
    </Frame>
  );
}

/* ── A-04 초안 만드는 중: 에이전트 단계 (서버 상태 + 화면에서 단계를 차례로 보여 줌) ── */
function Progress({ jobId, onDone }: { jobId: string; onDone: () => void }) {
  const { user } = useSession();
  const qc = useQueryClient();
  const job = useDraftJob(jobId);
  const regen = useRegenerate();
  const st = job.data?.draft_status ?? "queued";
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const t = setInterval(() => setShown((s) => Math.min(s + 1, 3)), 700);
    return () => clearInterval(t);
  }, []);
  /* queued·running이 시작한 지 300초(DAILY_NOTE_WRITER_TIMEOUT)를 넘기면 서버가 다시 접수할 수 있다 (3.26) */
  const [late, setLate] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setLate(true), 300_000);
    return () => clearTimeout(t);
  }, []);
  const step = st === "succeeded" ? shown : Math.min(shown, st === "running" ? 2 : 1);
  useEffect(() => {
    if (st === "succeeded" && step >= 3) qc.invalidateQueries({ queryKey: ["notes", user?.classroom_ids[0], todayKST()] }).then(onDone);
  }, [st, step, qc, user, onDone]);
  const rows: [string, string, string][] = [
    ["", "오늘 자료 모으기", "반 활동 · 관찰 기록 · 식단표"],
    ["", "아이별 문장 만들기", "아이마다 필요한 내용만 정리해요"],
    ["", "기록과 내용 확인하기", "다른 아이 내용과 빠진 요청을 확인해요"],
    ["", "다 됐어요", "이제 확인할 내용만 보여 드릴게요"],
  ];
  return (
    <Frame title="알림장 만들기">
      {st === "failed" ? (
        <section className="mt-4 grid gap-3 rounded-lg bg-card p-4 shadow-card">
          <b className="text-headline">초안을 만들지 못했어요</b>
          <p className="text-callout text-ink2">{job.data?.error?.message ?? "잠시 뒤 다시 만들어 주세요."} 관찰 기록은 그대로 있어요.</p>
          <SubButton onClick={() => regen.mutate(jobId)} disabled={regen.isPending}>{regen.isPending ? "다시 접수하는 중…" : "다시 만들기"}</SubButton>
        </section>
      ) : (
        <section className="mt-4 rounded-lg bg-card p-4 shadow-card">
          <b className="text-callout">초안을 만들고 있어요</b>
          <ol className="mt-3 grid gap-3">
            {rows.map(([who, t, d], i) => (
              <li key={t} className="grid grid-cols-[16px_1fr] gap-3">
                <span className={`mt-1 size-3.5 rounded-full border-2 ${i < step ? "border-accent bg-accent" : i === step ? "border-accent shadow-[0_0_0_3px_var(--tint)]" : "border-fill2"}`} />
                <span>
                  {who && <span className="block text-caption font-bold text-lav">{who}</span>}
                  <span className="block text-callout font-semibold">{t}</span>
                  <span className="block text-caption text-ink2">{d}</span>
                </span>
              </li>
            ))}
          </ol>
          <p className="mt-3 text-footnote text-ink2">다른 화면으로 가도 계속 만들어요. 다 되면 알려 드려요.</p>
          {late && st !== "succeeded" && (
            <div className="mt-3 flex items-center justify-between gap-2 rounded-md bg-g p-3 text-footnote">
              <span>오래 걸리고 있어요. 멈춘 것 같으면 다시 접수할 수 있어요.</span>
              <SubButton small onClick={() => regen.mutate(jobId)} disabled={regen.isPending}>다시 만들기</SubButton>
            </div>
          )}
        </section>
      )}
      <Dock>
        <PrimaryButton disabled loading={st !== "failed"}>
          만드는 중
        </PrimaryButton>
      </Dock>
    </Frame>
  );
}

/* ── A-05 걸린 아이만: 검사 AI가 짚은 아이 → 기록 없는 아이 → 검사 통과(접힘) ── */
function Review({ notes }: { notes: DailyNote[] }) {
  const { user } = useSession();
  const cid = user!.classroom_ids[0];
  const date = todayKST();
  const nav = useNavigate();
  const kids = useChildren(cid);
  const names = useMemo(() => Object.fromEntries((kids.data ?? []).map((k) => [k.id, k.display_name])), [kids.data]);
  const photos = useMemo(() => Object.fromEntries((kids.data ?? []).map((k) => [k.id, k.profile_photo])), [kids.data]);
  const { records, add } = useRecords(cid, date);
  const patch = usePatchNote(cid, date);
  const send = useSendNotes(cid, date);
  const toast = useToast();
  const [sheet, setSheet] = useState(false);
  const [busy, setBusy] = useState(false);
  const [showClean, setShowClean] = useState(false);
  /* "문제 없음으로 옮기기" 표시는 새로고침해도 남도록 이 기기에 둔다 (확인 전 단계라 서버 데이터는 아님) */
  const plainKey = `yuchion.plainOk.${cid}.${date}`;
  const [plainOk, setPlainOkRaw] = useState<Record<string, boolean>>(() => {
    try { return JSON.parse(localStorage.getItem(plainKey) ?? "{}"); } catch { return {}; }
  });
  const setPlainOk = (fn: (p: Record<string, boolean>) => Record<string, boolean>) =>
    setPlainOkRaw((p) => {
      const next = fn(p);
      try { localStorage.setItem(plainKey, JSON.stringify(next)); } catch { /* 저장이 막혀도 이번 화면에서는 동작 */ }
      return next;
    });
  const [writeFor, setWriteFor] = useState<DailyNote | null>(null);
  const lastWrite = useRef<DailyNote | null>(null);
  if (writeFor) lastWrite.current = writeFor;
  const shownWrite = writeFor ?? lastWrite.current; /* 닫히는 동안에도 시트를 둔다 */
  const regen = useRegenerate();
  const [regenSheet, setRegenSheet] = useState(false);
  const [inputId, setInputId] = useState(() => loadInputId(cid, date));
  /* 알림장 목록이 항목마다 input_id를 주므로, 다른 기기에서 만든 알림장도 이 값으로 이어 받는다 */
  const serverInputId = notes.find((n) => n.input_id)?.input_id;
  useEffect(() => {
    if (serverInputId && serverInputId !== inputId) { saveInputId(cid, date, serverInputId); setInputId(serverInputId); }
  }, [serverInputId, inputId, cid, date]);
  /* 보내기가 409 NOTE_BATCH_BLOCKED로 막혔을 때 details.blocked[]를 보여 준다. 빈 목록은 초안 작업이 만드는 중(queued·running)이거나 실패(failed)일 때 온다 (3.19) */
  const draftJob = useDraftJob(inputId ?? undefined);
  const [blocked, setBlocked] = useState<{ note_id: string; child_id: string; open_checks?: { problem?: string }[] }[] | null>(null);

  /* 다시 만들기: 보낸 알림장이 하나라도 있으면 서버가 409 INVALID_TRANSITION으로 막는다 (API 3.26) */
  const runRegen = () => {
    if (!inputId) return;
    regen.mutate(inputId, {
      onSuccess: (r) => {
        setRegenSheet(false);
        setBlocked(null);
        toast({ kind: "ok", title: "초안을 다시 만들고 있어요", sub: r.kept_edited ? `고친 알림장 ${r.kept_edited}개는 그대로 두었어요` : undefined });
      },
      onError: (e) => {
        setRegenSheet(false);
        if (e instanceof ApiError && e.status === 409) toast({ kind: "error", title: "다시 만들 수 없어요", sub: "이미 보낸 알림장이 있어요. 보낸 알림장은 새로 만들 수 없어요" });
        else toast({ kind: "error", title: "초안을 다시 만들지 못했어요", sub: "관찰 기록은 그대로 있어요.\n잠시 뒤 다시 눌러 주세요", action: { label: "다시 시도", run: runRegen } });
      },
    });
  };
  const c = { needs_check: 0, draft: 0, ready: 0, sent: 0 };
  notes.forEach((n) => c[n.status]++);
  const allSent = c.sent === notes.length;
  const hasChild = (n: DailyNote) => n.content.items.some((i) => i.key === "child");
  const flagged = notes.filter((n) => n.status === "needs_check");
  const noRecord = notes.filter((n) => n.status === "draft" && !hasChild(n) && !plainOk[n.id]);
  const clean = notes.filter((n) => n.status === "draft" && (hasChild(n) || plainOk[n.id]));
  const notReady = notes.filter((n) => n.status === "needs_check" || n.status === "draft").length;

  /* 한꺼번에 확인하는 API가 없어서 아이마다 PATCH를 차례로 부른다 */
  const confirmClean = async () => {
    setBusy(true);
    let ok = 0;
    for (const n of clean) {
      try {
        await patch.mutateAsync({ id: n.id, body: { confirm: true } });
        ok++;
      } catch {
        /* 실패한 아이는 목록에 남는다 */
      }
    }
    setBusy(false);
    toast({ kind: "ok", title: `${ok}명 알림장을 확인했어요` });
  };

  /* 기록 없는 아이에게 한 줄을 쓰면 오늘 기록에도 남기고, 그 아이 알림장에 child 줄로 넣는다 */
  const writeLine = (n: DailyNote, text: string) => {
    add(n.child_id, text);
    const items: NoteItem[] = [...n.content.items, { key: "child", label: "아이 메모", value: text, source: { type: "teacher_input" } }];
    patch.mutate({ id: n.id, body: { content: { items } } }, { onSuccess: () => toast({ kind: "ok", title: `${nameI(names[n.child_id] ?? "아이")} 한 줄을 넣었어요` }) });
  };

  const sendLock = useRef(false); /* 같은 순간 두 번 눌려도 발송 요청은 한 번만 보낸다 */
  const doSend = () => {
    if (sendLock.current) return;
    sendLock.current = true;
    send.mutate(undefined, {
      onSettled: () => { sendLock.current = false; },
      onSuccess: (r) => {
        setSheet(false);
        toast({ kind: "ok", title: `${r.sent_count}가정에 알림장을 보냈어요`, sub: "보호자 홈 '오늘 알림장'에 올라갔어요" });
        /* 시트가 닫히며 쌓아 둔 뒤로가기 기록을 먼저 정리한 다음 홈으로 간다 */
        window.setTimeout(() => nav("/teacher/home"), 150);
      },
      onError: (e) => {
        setSheet(false);
        const isBlocked = e instanceof ApiError && e.code === "NOTE_BATCH_BLOCKED";
        const list = isBlocked ? (((e.details as { blocked?: typeof blocked })?.blocked ?? []) as NonNullable<typeof blocked>) : [];
        if (isBlocked) { setBlocked(list); draftJob.refetch(); }
        toast({
          kind: "error",
          title: isBlocked ? (list.length ? `확인이 안 끝난 알림장이 ${list.length}개 있어요` : "확인이 안 끝난 알림장이 있어요") : "알림장을 보내지 못했어요",
          sub: isBlocked ? "표시된 아이를 먼저 확인해 주세요" : "연결을 확인하고 다시 보내 주세요",
        });
      },
    });
  };

  /* 답장의 요청 ID로 받은함 카드를 찾는다. 아직 목록에 없으면 받은함으로 보낸다 */
  const allCards = useAllCards();
  const replyCard = (requestId: string) => {
    const card = allCards.find((c) => c.requestId === requestId);
    return card ? `/teacher/inbox/${card.id}` : "/teacher/inbox";
  };

  const row = (n: DailyNote, sub: string, right?: React.ReactNode) => {
    const st = NOTE_STATUS[n.status];
    return (
      <li key={n.id} className="flex min-h-14 items-center gap-3 px-3 py-2 [&+&]:border-t [&+&]:border-sep">
        <ChildAvatar name={names[n.child_id] ?? "?"} photo={photos[n.child_id]} size={32} textClass="text-footnote" rounded="rounded-sm" />
        <div className="min-w-0 flex-1">
        <Link to={`/teacher/notes/${n.id}`} className="block">
          <span className="flex items-baseline gap-2">
            <b className="text-headline font-semibold">{names[n.child_id] ?? "아이"}</b>
            {!(allSent && n.status === "sent") && <span className={`text-caption font-bold ${st.cls}`}>{st.label}</span>}
            {n.supplies_checked_at && <span className="shrink-0 rounded-full bg-ok-tint px-2 py-0.5 text-caption font-bold text-ok">준비물 챙김</span>}
          </span>
          <span className="block truncate text-footnote text-ink2">{sub}</span>
        </Link>
          {!!n.replies?.length && (
            /* 학부모 답장은 새 문의로 접수되어 받은함 카드로 온다. 누르면 그 카드로 간다 */
            <Link to={replyCard(n.replies[n.replies.length - 1].request_id)} className="mt-0.5 flex items-center gap-1.5 text-footnote">
              <span className="shrink-0 rounded-full bg-tint px-2 py-0.5 text-caption font-bold text-accent-ink">답장 {n.replies.length}</span>
              <span className="min-w-0 truncate font-semibold text-accent-ink">{n.replies[n.replies.length - 1].body}</span>
            </Link>
          )}
        </div>
        {right ?? <Icon name="chevR" className="size-4 text-ink2" />}
      </li>
    );
  };

  const preview = notes.find((n) => hasChild(n)) ?? notes[0];
  /* 보내기 전 확인에는 아이 이름 없이 반 활동·식단·준비물 같은 공통 내용만 보여 준다 */
  const common = (preview?.content.items ?? []).filter((it) => COMMON_KEYS.includes(it.key) && it.value.trim());
  return (
    <Frame title="알림장 확인" sub={`${user?.display_name} · ${notes.length}명${allSent ? "" : " · 17:00까지"}`}>
      {!allSent && <section className="mt-4 rounded-lg bg-card p-3 shadow-card">
        <Meter parts={[[c.sent, "bg-ok"], [c.ready, "bg-lav"], [c.needs_check, "bg-accent"], [c.draft, "bg-ink3"]]} total={notes.length} />
        <div className="flex flex-wrap gap-x-3 text-footnote text-ink2">
          {allSent ? (
            <span>
              보냄 <b className="text-ink tabular-nums">{c.sent}</b>
            </span>
          ) : (
            <>
              <span>확인 필요 <b className="text-ink tabular-nums">{c.needs_check}</b></span>
              <span>문제 없음 <b className="text-ink tabular-nums">{c.draft}</b></span>
              <span>확인함 <b className="text-ink tabular-nums">{c.ready}</b></span>
            </>
          )}
        </div>
      </section>}

      {blocked && !allSent && (
        <section role="alert" className="mt-4 rounded-lg bg-danger-tint p-3 text-callout">
          <b className="text-danger">보내기가 막혔어요</b>
          {blocked.length ? (
            <ul className="mt-1.5 grid gap-1 text-footnote text-ink">
              {blocked.map((b) => (
                <li key={b.note_id}>
                  <Link to={`/teacher/notes/${b.note_id}`} className="font-semibold underline">{names[b.child_id] ?? "아이"}</Link>
                  <span className="text-ink2"> · {b.open_checks?.map((o) => o.problem).filter(Boolean).join(", ") || "확인 필요"}</span>
                </li>
              ))}
            </ul>
          ) : draftJob.data?.draft_status === "failed" ? (
            <div className="mt-1.5 grid gap-2">
              <p className="text-footnote text-ink2">초안을 만들지 못했어요. 관찰 기록은 그대로 있어요.</p>
              <SubButton small onClick={() => setRegenSheet(true)}>다시 만들기</SubButton>
            </div>
          ) : (
            <p className="mt-1 text-footnote text-ink2">초안이 아직 만들어지는 중이에요. 잠시 뒤 다시 보내 주세요.</p>
          )}
        </section>
      )}

      {!allSent && inputId && (
        <div className="mt-3 flex items-center justify-between gap-2 px-1 text-footnote text-ink2">
          {c.sent > 0 ? (
            <span>보낸 알림장이 있어서 다시 만들 수 없어요</span>
          ) : (
            <>
              <span>초안이 마음에 안 들면 확인하지 않은 아이만 다시 만들 수 있어요</span>
              <SubButton small tone="gray" className="shrink-0 whitespace-nowrap" onClick={() => setRegenSheet(true)}>다시 만들기</SubButton>
            </>
          )}
        </div>
      )}

      {!allSent && flagged.length > 0 && (
        <>
          <Label right={<span>{flagged.length}명</span>}>먼저 확인할 아이</Label>
          <ul className="overflow-hidden rounded-lg bg-card shadow-card">{flagged.map((n) => row(n, n.open_checks.map((o) => CHECK_KIND[o.kind]?.short ?? o.problem).join(" · ")))}</ul>
        </>
      )}

      {!allSent && noRecord.length > 0 && (
        <>
          <Label
            right={
              <span className="flex items-center gap-2">
                {noRecord.length}명
                <SubButton small tone="gray" onClick={() => setPlainOk((p) => ({ ...p, ...Object.fromEntries(noRecord.map((n) => [n.id, true])) }))}>
                  모두 문제 없음으로 옮기기
                </SubButton>
              </span>
            }
          >
            반 활동만 작성된 아이
          </Label>
          <ul className="overflow-hidden rounded-lg bg-card shadow-card">
            {noRecord.map((n) =>
              row(
                n,
                "반 활동만 들어갔어요",
                <span className="flex shrink-0 gap-1">
                  <SubButton small onClick={() => setWriteFor(n)}>
                    내용 추가
                  </SubButton>
                  <SubButton small tone="gray" onClick={() => setPlainOk((p) => ({ ...p, [n.id]: true }))}>
                    문제 없음으로
                  </SubButton>
                </span>,
              ),
            )}
          </ul>
        </>
      )}

      {!allSent && (
        <>
          <Label right={<span>{clean.length}명</span>}>확인할 문제 없음</Label>
          <section className="overflow-hidden rounded-lg bg-card shadow-card">
            {showClean && <ul>{clean.map((n) => row(n, n.content.items.find((i) => i.key === "child")?.value ?? "반 활동만 들어갔어요"))}</ul>}
            <div className={`flex items-center justify-between gap-2 px-3 py-2.5 ${showClean && clean.length ? "border-t border-sep" : ""}`}>
              <button className="inline-flex min-h-9 items-center gap-1 text-footnote font-semibold text-ink2" onClick={() => setShowClean((v) => !v)} aria-expanded={showClean}>
                {showClean ? "접기" : "펼쳐 보기"}
                <Icon name={showClean ? "chevL" : "chevR"} className="size-3.5 rotate-90" />
              </button>
              {clean.length ? (
                <SubButton onClick={confirmClean} disabled={busy}>
                  {busy ? "확인하는 중…" : `${clean.length}명 모두 확인`}
                </SubButton>
              ) : (
                <span className="text-caption font-bold text-lav">확인할 아이가 없어요</span>
              )}
            </div>
          </section>
          {c.ready > 0 && (
            <>
              <Label right={<span>{c.ready}명</span>}>확인함</Label>
              <ul className="overflow-hidden rounded-lg bg-card shadow-card">{notes.filter((n) => n.status === "ready").map((n) => row(n, n.content.items.find((i) => i.key === "child")?.value ?? "반 활동만 들어갔어요"))}</ul>
            </>
          )}
        </>
      )}

      {allSent && (
        <>
          <Label right={<span>{c.sent}명</span>}>보냈어요</Label>
          <ul className="overflow-hidden rounded-lg bg-card shadow-card">{notes.map((n) => row(n, n.content.items.find((i) => i.key === "child")?.value ?? "반 활동만 들어갔어요"))}</ul>
        </>
      )}

      {!allSent && (
        <Dock reason={notReady ? `아직 확인 안 한 알림장 ${notReady}개` : `${notes.length}명 모두 확인했어요`} reasonIcon={notReady ? "lock" : "check"}>
          <PrimaryButton disabled={!!notReady} onClick={() => setSheet(true)}>
            {notes.length}명에게 한 번에 보내기
          </PrimaryButton>
        </Dock>
      )}

      {/* A-07 일괄 발송 시트 */}
      <Sheet open={sheet} onClose={() => setSheet(false)} title={`${notes.length}명에게 한 번에 보내기`}>
        <p className="text-footnote text-ink2">반 전체 {notes.length}명에게 보내요. 아이별 내용은 그 아이의 보호자에게만 가요. 보낸 뒤에는 정정으로만 고칠 수 있어요</p>
        {common.length > 0 && (
          <div className="grid gap-1 rounded-lg bg-g p-3 text-callout">
            <b className="text-headline">모든 가정에 들어가는 내용</b>
            {common.map((it, i) => (
              <span key={i}>
                <b className="mr-1.5 text-footnote text-ink2">{itemLabel(it)}</b>
                {noMd(it.value)}
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

      <Sheet open={regenSheet} onClose={() => setRegenSheet(false)} title="초안 다시 만들기">
        <p className="text-callout text-ink2">내가 고친 알림장과 이미 확인한 알림장은 그대로 두고, 나머지만 새로 써요.</p>
        <p className="rounded-md bg-g p-3 text-footnote text-ink2">처음 접수한 반 활동·준비물·아이별 메모로 다시 만들어요. 그 뒤에 새로 쓴 관찰 기록은 반영되지 않으니, 필요한 내용은 아이 상세에서 직접 추가해 주세요. 식단과 보호자 요청은 다시 모아요.</p>
        <div className="grid grid-cols-[1fr_2fr] gap-2">
          <SubButton tone="gray" className="h-[52px]" onClick={() => setRegenSheet(false)}>취소</SubButton>
          <PrimaryButton loading={regen.isPending} onClick={runRegen}>
            다시 만들기
          </PrimaryButton>
        </div>
      </Sheet>

      {shownWrite && (
        <RecordSheet
          key={shownWrite.id}
          open={!!writeFor}
          name={names[shownWrite.child_id] ?? "아이"}
          entries={records[shownWrite.child_id] ?? []}
          onClose={() => setWriteFor(null)}
          onSave={(t) => writeLine(shownWrite, t)}
        />
      )}
    </Frame>
  );
}
