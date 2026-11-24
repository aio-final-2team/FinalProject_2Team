import { useEffect, useMemo, useState } from "react";
import { ApiError } from "@/api/client";
import { MAX_PHOTOS, MAX_PHOTO_BYTES, PHOTO_TYPES, useCreatePost, type Lane } from "@/api/feed";
import { PrimaryButton, SubButton } from "@/components/Dock";
import { Sheet } from "@/components/Sheet";
import { useToast } from "@/components/Toast";

export type Kid = { id: string; display_name: string };

/**
 * 글·사진 올리기 (API 39·41). 사진 AI가 붙기 전에는 올리는 사람이 나온 아이를 직접 고른다.
 * 아이를 고르지 않으면 사진은 그 칸을 볼 수 있는 모두에게 보인다 (문서 3.29).
 */
export function ComposeSheet({ open, onClose, lane, kids, laneLabel }: { open: boolean; onClose: () => void; lane?: Lane; kids: Kid[]; laneLabel: string }) {
  const create = useCreatePost(lane);
  const toast = useToast();
  const [body, setBody] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [picked, setPicked] = useState<string[]>([]);
  const [err, setErr] = useState("");
  const previews = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => previews.forEach((u) => URL.revokeObjectURL(u)), [previews]);

  const reset = () => { setBody(""); setFiles([]); setPicked([]); setErr(""); };
  const close = () => { reset(); onClose(); };

  const addFiles = (list: FileList | null) => {
    if (!list) return;
    const next = [...files];
    for (const f of Array.from(list)) {
      if (!PHOTO_TYPES.includes(f.type)) { setErr("사진은 jpg, png, webp만 올릴 수 있어요"); continue; }
      if (f.size > MAX_PHOTO_BYTES) { setErr("사진 한 장은 5MB까지 올릴 수 있어요"); continue; }
      if (next.length >= MAX_PHOTOS) { setErr(`사진은 ${MAX_PHOTOS}장까지 올릴 수 있어요`); break; }
      next.push(f);
      setErr("");
    }
    setFiles(next);
  };

  const submit = () =>
    create.mutate(
      { body: body.trim(), files, tags: files.map(() => picked) },
      {
        onSuccess: () => { toast({ kind: "ok", title: "올렸어요", sub: laneLabel }); close(); },
        onError: (e) => {
          if (e instanceof ApiError && e.status === 403) toast({ kind: "error", title: "여기에는 글을 올릴 수 없어요", sub: "내 반이나 내 원에서만 올릴 수 있어요" });
          else if (e instanceof ApiError && (e.status === 413 || e.status === 422)) toast({ kind: "error", title: "글이나 사진을 올리지 못했어요", sub: "사진은 10장까지, 한 장에 5MB까지 올릴 수 있어요" });
          else toast({ kind: "error", title: "올리지 못했어요", sub: "연결을 확인하고 다시 눌러 주세요", action: { label: "다시 시도", run: submit } });
        },
      },
    );

  return (
    <Sheet open={open} onClose={close} title="글 올리기">
      <p className="text-footnote text-ink2">{laneLabel}에 올라가요</p>
      <label className="grid gap-1.5">
        <span className="text-footnote font-semibold">내용</span>
        <textarea value={body} onChange={(e) => setBody(e.target.value)} maxLength={2000} rows={4} placeholder="함께 나누고 싶은 이야기를 적어 주세요" className="rounded-md border-[1.5px] border-line bg-card px-3 py-2.5 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
      </label>
      <div className="grid gap-2">
        <span className="text-footnote font-semibold">사진 {files.length > 0 && <span className="tabular-nums text-ink2">({files.length}/{MAX_PHOTOS})</span>}</span>
        {previews.length > 0 && (
          <ul className="flex gap-2 overflow-x-auto pb-1" aria-label="고른 사진">
            {previews.map((u, i) => (
              <li key={u} className="relative shrink-0">
                <img src={u} alt={`고른 사진 ${i + 1}`} className="size-16 rounded-md object-cover" />
                <button type="button" aria-label={`사진 ${i + 1} 빼기`} onClick={() => setFiles((fs) => fs.filter((_, j) => j !== i))} className="absolute -right-1.5 -top-1.5 grid size-6 place-items-center rounded-full bg-ink text-card">
                  <svg viewBox="0 0 24 24" className="size-3" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden><path d="M6 6l12 12M18 6L6 18" /></svg>
                </button>
              </li>
            ))}
          </ul>
        )}
        <label className="inline-flex h-11 cursor-pointer items-center justify-center rounded-md bg-tint px-4 text-callout font-semibold text-accent-ink active:scale-[.97]">
          사진 고르기
          <input type="file" accept={PHOTO_TYPES.join(",")} multiple className="sr-only" onChange={(e) => { addFiles(e.target.files); e.target.value = ""; }} />
        </label>
      </div>
      {files.length > 0 && kids.length > 0 && (
        <div className="grid gap-2" role="group" aria-label="사진에 나온 아이">
          <span className="text-footnote font-semibold">사진에 나온 아이</span>
          <div className="flex flex-wrap gap-2">
            {kids.map((k) => {
              const on = picked.includes(k.id);
              return (
                <button key={k.id} type="button" aria-pressed={on} onClick={() => setPicked((p) => (on ? p.filter((x) => x !== k.id) : [...p, k.id]))} className={`h-9 rounded-full border px-3 text-footnote font-semibold ${on ? "border-accent bg-tint text-accent-ink" : "border-sep bg-card"}`}>
                  {k.display_name}
                </button>
              );
            })}
          </div>
          <p className="text-caption text-ink2">고른 아이의 공개 범위가 사진에 적용돼요. 고르지 않으면 {laneLabel}을 볼 수 있는 모두에게 보여요.</p>
        </div>
      )}
      {err && <p role="alert" className="text-footnote font-medium text-danger">{err}</p>}
      <div className="grid grid-cols-[1fr_2fr] gap-2">
        <SubButton tone="gray" className="h-[52px]" onClick={close}>닫기</SubButton>
        <PrimaryButton loading={create.isPending} disabled={!body.trim()} onClick={submit}>올리기</PrimaryButton>
      </div>
    </Sheet>
  );
}
