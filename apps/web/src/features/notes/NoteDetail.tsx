import { ScreenTop } from "@/components/ScreenTop";
import { useMemo, useState } from "react";
import { QueryState } from "@/components/QueryState";
import { Link, useNavigate, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ApiError, api } from "@/api/client";
import { useChildren, useNotes, usePatchNote } from "@/api/notes";
import { CorrectSheet } from "./CorrectSheet";
import { useSession } from "@/app/session";
import { Dock, PrimaryButton, SubButton } from "@/components/Dock";
import { Icon } from "@/components/Icon";
import { useToast } from "@/components/Toast";
import { useRecords } from "@/features/records/store";
import { fmtDateTime } from "@/domain/datetime";
import { CHECK_KIND, NOTE_STATUS, SOURCE_LABEL, dateLabel, nameI, todayKST, type DailyNote, type NoteItem, type OpenCheck } from "@/domain/notes";

/**
 * 아이별 알림장 (API 25 PATCH). 줄마다 출처, 검사 AI가 짚은 곳(open_checks[].kind),
 * AI 초안 테두리(디자인 시스템 7.16), 확인하면 ready, 보내기 전까지 되돌릴 수 있다.
 */
export function NoteDetail() {
  const { noteId } = useParams();
  const { user } = useSession();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const notes = useNotes(cid, date);
  const kids = useChildren(cid);
  const names = useMemo(() => Object.fromEntries((kids.data ?? []).map((k) => [k.id, k.display_name])), [kids.data]);
  const note = notes.data?.find((n) => n.id === noteId);

  if (notes.isLoading || (notes.isError && notes.data === undefined))
    return (
      <div className="mx-auto max-w-[680px] px-4 pt-6">
        <QueryState queries={[notes]} errorTitle="알림장을 불러오지 못했어요">{null}</QueryState>
      </div>
    );
  if (!note)
    return (
      <div className="mx-auto max-w-[680px] px-4 pt-10">
        <p className="text-callout text-ink2">이 알림장을 찾지 못했어요.</p>
        <Link to="/teacher/notes" className="mt-3 inline-block font-semibold text-accent">
          오늘 알림장으로
        </Link>
      </div>
    );
  return <Detail key={note.id} note={note} notes={notes.data!} name={names[note.child_id] ?? "아이"} names={names} />;
}

function Detail({ note, notes, name, names }: { note: DailyNote; notes: DailyNote[]; name: string; names: Record<string, string> }) {
  const { user } = useSession();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const patch = usePatchNote(cid, date);
  const toast = useToast();
  const nav = useNavigate();
  const [items, setItems] = useState<NoteItem[]>(note.content.items);
  const [editing, setEditing] = useState<number | null>(null);
  const [draftText, setDraftText] = useState("");
  const [err, setErr] = useState("");
  const open = note.open_checks;
  const locked = note.status === "sent";
  const [correcting, setCorrecting] = useState(false);
  const next = notes.find((n) => n.status === "needs_check" && n.id !== note.id);
  const { records } = useRecords(cid, date);
  const entries = records[note.child_id] ?? [];
  const memoLine = note.content.items.find((i) => i.key === "child")?.value;

  const save = (body: Parameters<typeof patch.mutate>[0]["body"], done?: string) =>
    patch.mutate(
      { id: note.id, body },
      {
        onSuccess: () => {
          setErr("");
          if (done) toast({ kind: "ok", title: done });
        },
        onError: (e) => setErr(e instanceof ApiError ? e.message : "저장하지 못했어요. 다시 눌러 주세요."),
      },
    );

  /* 걸린 문장을 그 줄에서 빼고, 확인 항목을 해결로 보낸다 */
  const removeSentence = (c: OpenCheck) => {
    const nextItems = items.map((it) => (it.key === c.item_key && c.sentence ? { ...it, value: it.value.replace(c.sentence, "").replace(/\s{2,}/g, " ").trim() } : it));
    setItems(nextItems);
    save({ content: { items: nextItems }, resolved_checks: [c.id] }, "문장을 뺐어요");
  };
  const keep = (c: OpenCheck) => save({ resolved_checks: [c.id] }, "확인할 곳을 해결했어요");
  /* 빠진 보호자 요청은 요청 원문을 읽어 그 줄(귀가·투약·오늘 하루)로 넣는다 */
  const missed = open.find((c) => c.kind === "request_missed" && c.request_id);
  const req = useQuery({
    queryKey: ["request", missed?.request_id],
    queryFn: () => api<{ request: { type: string; title: string }; messages: { body: string; sender_type: string }[] }>(`/api/v1/requests/${missed!.request_id}`),
    enabled: !!missed,
  });
  const addRequest = (c: OpenCheck) => {
    const body = req.data?.messages.find((m) => m.sender_type === "user")?.body ?? req.data?.request.title;
    if (!body) return;
    const label = c.item_key === "pickup" ? "귀가" : c.item_key === "medication" ? "투약" : "보호자 요청";
    const nextItems = [...items, { key: c.item_key, label, value: body, source: { type: "request" as const, request_id: c.request_id ?? null } }];
    setItems(nextItems);
    save({ content: { items: nextItems }, resolved_checks: [c.id] }, `${label} 줄을 넣었어요`);
  };
  const saveEdit = (i: number) => {
    const nextItems = items.map((it, j) => (j === i ? { ...it, value: draftText.trim() } : it));
    setItems(nextItems);
    setEditing(null);
    save({ content: { items: nextItems }, resolved_checks: open.filter((c) => c.item_key === items[i].key).map((c) => c.id) }, "고친 내용을 저장했어요");
  };
  const confirm = () =>
    patch.mutate(
      { id: note.id, body: { confirm: true } },
      {
        onSuccess: () => {
          toast({
            kind: "undo",
            title: `${nameI(name)} 알림장을 확인했어요`,
            sub: "보내기 전까지 다시 고칠 수 있어요",
            action: { label: "되돌리기", run: () => patch.mutate({ id: note.id, body: { confirm: false } }) },
          });
          if (next) nav(`/teacher/notes/${next.id}`);
          else nav("/teacher/notes");
        },
        onError: (e) => setErr(e instanceof ApiError ? e.message : "확인하지 못했어요. 다시 눌러 주세요."),
      },
    );

  const st = NOTE_STATUS[note.status];
  return (
    <div className="mx-auto max-w-[680px] px-4 pb-48 pt-2 lg:pb-10 lg:pt-6">
      <ScreenTop back={{ to: "/teacher/notes", label: "오늘 알림장" }} title={`${nameI(name)} 알림장`} sub={<>{user?.display_name} · {dateLabel(note.note_date)} · <span className={`font-bold ${st.cls}`}>{st.label}</span></>} />
      <div className="mb-4" />

      <div className="mb-2 px-1 text-footnote font-semibold text-ink2">오늘 기록</div>
      <div className="mb-4 rounded-lg bg-g px-3 py-2.5 text-callout">
        {entries.length ? (
          <ul className="grid gap-1">
            {entries.map((e, i) => (
              <li key={i} className="flex gap-2">
                <time className="text-footnote text-ink2 tabular-nums">{e.at}</time>
                <span>{e.text}</span>
              </li>
            ))}
          </ul>
        ) : memoLine ? (
          <span>{memoLine}</span>
        ) : (
          <span className="text-ink2">기록이 없어서 반 활동만 들어갔어요</span>
        )}
      </div>

      {open.length > 0 && (
        <section className="mb-4 grid gap-2">
          <div className="flex justify-between px-1 text-footnote font-semibold text-ink2">
            <span>검사 AI가 짚은 곳</span>
            <span>{open.length}개 남음</span>
          </div>
          {open.map((c) => {
            const k = CHECK_KIND[c.kind] ?? { title: c.problem };
            const named = c.kind === "other_child" ? Object.values(names).find((n) => c.sentence?.includes(n)) : undefined;
            return (
              <div key={c.id} className="grid gap-2 rounded-lg bg-card p-3 shadow-card">
                <div className="flex gap-2">
                  <Icon name="ai" className="mt-0.5 size-5 shrink-0 text-accent" />
                  <div>
                    <b className="text-callout">{k.title}</b>
                    <p className="text-footnote text-ink2">
                      {c.problem}
                      {named ? ` (${named})` : ""}
                    </p>
                    {c.sentence && <p className="mt-1 rounded-sm bg-tint px-2 py-1 text-footnote">“{c.sentence}”</p>}
                  </div>
                </div>
                {!locked && (
                  <div className="flex flex-wrap gap-2">
                    {c.kind === "request_missed" && (
                      <SubButton small onClick={() => addRequest(c)} disabled={patch.isPending || !req.data}>
                        {req.isLoading ? "요청을 불러오는 중…" : `요청 내용 넣기${req.data ? ` · “${req.data.request.title}”` : ""}`}
                      </SubButton>
                    )}
                    {k.fix && c.sentence && (
                      <SubButton small onClick={() => removeSentence(c)} disabled={patch.isPending}>
                        {k.fix}
                      </SubButton>
                    )}
                    {k.keep && (
                      <SubButton small tone="gray" onClick={() => keep(c)} disabled={patch.isPending}>
                        {k.keep}
                      </SubButton>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      )}

      <div className="mb-2 px-1 text-footnote font-semibold text-ink2">보호자에게 보낼 내용</div>
      <section className="rounded-lg rounded-tr-xs border-[1.5px] border-accent bg-card p-3">
        <span className="text-caption font-bold text-accent-ink">AI 초안, 고칠 수 있어요</span>
        {items.map((it, i) => {
          const bad = open.some((c) => c.item_key === it.key && c.sentence && it.value.includes(c.sentence));
          const src = it.source.type === "document" ? it.source.document_title ?? "원 자료" : SOURCE_LABEL[it.source.type];
          return (
            <div key={i} className={`py-2.5 ${i ? "border-t border-sep" : ""}`}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-footnote font-semibold text-ink2">{it.key === "child" ? `${nameI(name)}의 오늘` : it.label}</span>
                {!locked && editing !== i && (
                  <button
                    className="text-footnote font-semibold text-accent"
                    onClick={() => {
                      setEditing(i);
                      setDraftText(it.value);
                    }}
                  >
                    고치기
                  </button>
                )}
              </div>
              {editing === i ? (
                <div className="mt-1 grid gap-2">
                  <textarea
                    value={draftText}
                    onChange={(e) => setDraftText(e.target.value)}
                    rows={3}
                    autoFocus
                    aria-label={`${it.label} 고치기`}
                    className="resize-none rounded-md border-[1.5px] border-accent bg-card px-3 py-2 text-body outline-none shadow-[0_0_0_3px_var(--tint)]"
                  />
                  <div className="flex justify-end gap-2">
                    <SubButton small tone="gray" onClick={() => setEditing(null)}>
                      취소
                    </SubButton>
                    <SubButton small onClick={() => saveEdit(i)} disabled={!draftText.trim()}>
                      저장
                    </SubButton>
                  </div>
                </div>
              ) : (
                <p className={`mt-0.5 text-body ${bad ? "rounded-xs bg-tint" : ""}`}>{it.value}</p>
              )}
              <span className={`mt-1 inline-block rounded-sm px-2 py-0.5 text-caption font-semibold ${it.source.type === "document" ? "bg-ok-tint text-ok" : it.source.type === "request" ? "bg-lav-tint text-lav" : "bg-g text-ink2"}`}>{src}</span>
            </div>
          );
        })}
      </section>
      {err && (
        <p role="alert" className="mt-2 text-footnote font-medium text-danger">
          {err}
        </p>
      )}

      {locked && (
        <div className="mt-4 grid gap-2">
          <p className="rounded-md bg-tint p-3 text-footnote text-accent-ink">{note.corrected_at ? `${fmtDateTime(note.corrected_at)}에 정정했어요` : "보낸 알림장이에요"}</p>
          <SubButton tone="gray" className="h-[52px] w-full" onClick={() => setCorrecting(true)}>잘못된 내용 정정하기</SubButton>
          <CorrectSheet note={note} open={correcting} onClose={() => setCorrecting(false)} cid={cid} date={date} />
        </div>
      )}
      {!locked && (
        <Dock reason={open.length ? `확인할 곳 ${open.length}개를 먼저 정리해 주세요` : note.status === "ready" ? "확인했어요. 반 전체를 보낼 때 함께 나가요" : undefined} reasonIcon={open.length ? "lock" : "check"}>
          {note.status === "ready" ? (
            <SubButton tone="gray" className="h-[52px] w-full" onClick={() => save({ confirm: false }, "확인을 취소했어요")}>
              확인 취소하기
            </SubButton>
          ) : (
            <PrimaryButton disabled={open.length > 0} loading={patch.isPending} onClick={confirm}>
              다 읽었어요
            </PrimaryButton>
          )}
        </Dock>
      )}
    </div>
  );
}
