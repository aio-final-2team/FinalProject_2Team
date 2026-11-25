import { useState } from "react";
import { ApiError } from "@/api/client";
import { DOC_FILE_TYPES, DOC_TYPE_LABEL, MAX_DOC_BYTES, VISIBILITY_LABEL, useUploadDocument } from "@/api/documents";
import { PrimaryButton, SubButton } from "@/components/Dock";
import { Sheet } from "@/components/Sheet";
import { useToast } from "@/components/Toast";
import { todayKST } from "@/domain/notes";

const TYPES = ["notice", "menu", "schedule", "policy"] as const;

/**
 * 자료 올리기 (API 27). 통신문·식단표·일정·운영 규정을 글 파일(.md·.txt)로 올린다. 올리면 서버가 조각으로 나눠 읽고,
 * 읽지 못하면 실패로 알려 준다. 담임은 우리 반 자료로, 원장은 원 전체 자료로 올라간다.
 */
export function UploadSheet({ open, onClose, classroomId }: { open: boolean; onClose: () => void; classroomId?: string }) {
  const up = useUploadDocument();
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const [type, setType] = useState<(typeof TYPES)[number]>("notice");
  const [vis, setVis] = useState("all");
  const [from, setFrom] = useState(todayKST());
  const [err, setErr] = useState("");

  const pick = (f: File | undefined) => {
    if (!f) return;
    if (f.size > MAX_DOC_BYTES) return setErr("파일은 2MB까지 올릴 수 있어요");
    if (!/\.(md|markdown|txt)$/i.test(f.name)) return setErr("글 파일(.md, .txt)만 올릴 수 있어요");
    setErr(""); setFile(f);
  };
  const close = () => { setFile(null); setErr(""); onClose(); };
  const submit = () =>
    file &&
    up.mutate(
      { file, doc_type: type, visibility: vis, classroom_ids: classroomId ? [classroomId] : [], effective_from: from },
      {
        onSuccess: (d) => {
          if (d.ingest_status === "failed") toast({ kind: "error", title: "자료를 읽지 못했어요", sub: "글 파일(.md, .txt)이 맞는지 확인해 주세요" });
          else toast({ kind: "ok", title: "자료를 올렸어요", sub: `${DOC_TYPE_LABEL[d.doc_type] ?? "자료"} · 조각 ${d.chunk_count}개로 읽었어요` });
          if (d.ingest_status !== "failed") close();
        },
        onError: (e) => toast({ kind: "error", title: e instanceof ApiError && (e.status === 413 || e.status === 422) ? "자료를 올리지 못했어요" : "올리지 못했어요", sub: e instanceof ApiError && (e.status === 413 || e.status === 422) ? "파일 크기와 날짜를 확인해 주세요" : "연결을 확인하고 다시 눌러 주세요" }),
      },
    );

  return (
    <Sheet open={open} onClose={close} title="자료 올리기">
      <p className="text-footnote text-ink2">{classroomId ? "우리 반 자료로 올라가요" : "원 전체 자료로 올라가요"}. 올리면 서버가 내용을 읽어 두어요.</p>
      <label className="inline-flex h-12 cursor-pointer items-center justify-center rounded-md bg-tint px-4 text-callout font-semibold text-accent-ink active:scale-[.97]">
        {file ? file.name : "글 파일 고르기"}
        <input type="file" accept={DOC_FILE_TYPES} className="sr-only" onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} />
      </label>
      <div className="grid gap-2" role="radiogroup" aria-label="자료 종류">
        <span className="text-footnote font-semibold">종류</span>
        <div className="flex flex-wrap gap-2">
          {TYPES.map((t) => <button key={t} type="button" role="radio" aria-checked={type === t} onClick={() => setType(t)} className={`h-9 rounded-full border px-3 text-footnote font-semibold ${type === t ? "border-accent bg-tint text-accent-ink" : "border-sep bg-card"}`}>{DOC_TYPE_LABEL[t]}</button>)}
        </div>
      </div>
      <div className="grid gap-2" role="radiogroup" aria-label="공개 범위">
        <span className="text-footnote font-semibold">누가 볼 수 있나요</span>
        <div className="flex flex-wrap gap-2">
          {Object.entries(VISIBILITY_LABEL).map(([k, v]) => <button key={k} type="button" role="radio" aria-checked={vis === k} onClick={() => setVis(k)} className={`h-9 rounded-full border px-3 text-footnote font-semibold ${vis === k ? "border-accent bg-tint text-accent-ink" : "border-sep bg-card"}`}>{v}</button>)}
        </div>
      </div>
      <label className="grid gap-1.5">
        <span className="text-footnote font-semibold">적용 시작일</span>
        <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-12 rounded-md border-[1.5px] border-line bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
      </label>
      {err && <p role="alert" className="text-footnote font-medium text-danger">{err}</p>}
      <div className="grid grid-cols-[1fr_2fr] gap-2">
        <SubButton tone="gray" className="h-[52px]" onClick={close}>닫기</SubButton>
        <PrimaryButton loading={up.isPending} disabled={!file || !from} onClick={submit}>올리기</PrimaryButton>
      </div>
    </Sheet>
  );
}
