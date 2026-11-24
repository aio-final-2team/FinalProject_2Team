import { usePhotoScope, useSetPhotoScope, type PhotoScope } from "@/api/feed";
import { Sheet } from "@/components/Sheet";
import { useToast } from "@/components/Toast";

const OPTIONS: { key: PhotoScope; title: string; sub: string }[] = [
  { key: "family", title: "가족만", sub: "우리 아이 보호자와 올린 사람만 볼 수 있어요" },
  { key: "class", title: "우리 반까지", sub: "같은 반 보호자도 볼 수 있어요" },
  { key: "org", title: "원 전체까지", sub: "같은 원의 반·원 소식에서도 볼 수 있어요" },
];

/** 내 아이가 나온 사진을 누구까지 볼 수 있게 할지 (API 48·49). 보호자가 여럿이면 마지막 변경을 따른다 */
export function ScopeSheet({ open, onClose, kid }: { open: boolean; onClose: () => void; kid?: { id: string; display_name: string } }) {
  const q = usePhotoScope(open ? kid?.id : undefined);
  const set = useSetPhotoScope(kid?.id);
  const toast = useToast();
  const cur = q.data?.photo_scope;
  return (
    <Sheet open={open} onClose={onClose} title={`${kid?.display_name ?? "아이"} 사진 공개 범위`}>
      <p className="text-footnote text-ink2">{kid?.display_name ?? "아이"}가 나온 사진을 누가 볼 수 있는지 정해요.</p>
      <ul className="grid gap-2" role="radiogroup" aria-label="공개 범위">
        {OPTIONS.map((o) => (
          <li key={o.key}>
            <button
              type="button"
              role="radio"
              aria-checked={cur === o.key}
              disabled={q.isLoading || set.isPending}
              onClick={() => set.mutate(o.key, { onSuccess: () => toast({ kind: "ok", title: "공개 범위를 바꿨어요", sub: o.title }), onError: () => toast({ kind: "error", title: "공개 범위를 바꾸지 못했어요", sub: "연결을 확인하고 다시 눌러 주세요" }) })}
              className={`flex w-full items-center gap-3 rounded-lg border-[1.5px] p-3 text-left active:scale-[.99] disabled:opacity-60 ${cur === o.key ? "border-accent bg-tint" : "border-sep bg-card"}`}
            >
              <span aria-hidden className={`grid size-5 shrink-0 place-items-center rounded-full border-2 ${cur === o.key ? "border-accent" : "border-line"}`}>{cur === o.key && <span className="size-2.5 rounded-full bg-accent" />}</span>
              <span className="min-w-0 flex-1"><b className="block text-callout">{o.title}</b><span className="text-footnote text-ink2">{o.sub}</span></span>
            </button>
          </li>
        ))}
      </ul>
      {q.isError && <p role="alert" className="text-footnote text-danger">지금 공개 범위를 불러오지 못했어요. 다시 열어 주세요.</p>}
    </Sheet>
  );
}
