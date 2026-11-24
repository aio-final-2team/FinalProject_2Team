import { useState } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { useCreateRequest, type RequestType } from "@/api/requests";
import { Dock, PrimaryButton } from "@/components/Dock";
import { Icon } from "@/components/Icon";
import { ScreenTop } from "@/components/ScreenTop";

const TYPES: [RequestType, string, string][] = [
  ["inquiry", "문의", "궁금한 점을 물어봐요"],
  ["consultation", "상담", "선생님과 상담 시간을 잡아요"],
  ["complaint", "민원", "불편하거나 걱정되는 점을 알려요"],
];

/** P-03 새 요청 쓰기 (T21 뼈대). 투약·귀가는 T46에서 열려서 고르는 칸에 두지 않는다 */
export function NewRequestPage() {
  const nav = useNavigate();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<{ children: { id: string; display_name: string }[] }>("/api/v1/me") });
  const create = useCreateRequest();
  const [type, setType] = useState<RequestType>("inquiry");
  const [body, setBody] = useState("");
    const [err, setErr] = useState("");
  const child = me.data?.children[0]?.id; /* 아이가 여럿이면 고르는 칸을 더한다. 시연 계정은 한 명 */

  const submit = () => {
    if (!body.trim()) return setErr("어떤 내용인지 한 줄 이상 적어 주세요.");
    if (!child) return setErr("아이 정보를 불러오지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    setErr("");
    create.mutate(
      { type, body: body.trim(), child_id: child },
      { onSuccess: (r) => nav(`/parent/requests/${r.request.id}`, { replace: true }), onError: (e) => setErr(e instanceof ApiError ? e.message : "보내지 못했어요. 잠시 뒤 다시 눌러 주세요.") },
    );
  };

  return (
    <div className="px-4 pb-48">
      <ScreenTop audience="parent" back={{ to: "/parent/requests", label: "요청" }} title="새 요청" />
      <div className="mb-2 mt-5 px-1 text-footnote font-semibold text-ink2">무엇을 도와 드릴까요?</div>
      <div role="radiogroup" className="grid gap-2">
        {TYPES.map(([v, label, desc]) => (
          <button key={v} role="radio" aria-checked={type === v} onClick={() => setType(v)} className={`flex min-h-14 items-center justify-between gap-3 rounded-lg bg-card px-3 py-2.5 text-left shadow-card ${type === v ? "outline outline-2 -outline-offset-2 outline-accent" : ""}`}>
            <span>
              <b className="block text-headline font-semibold">{label}</b>
              <span className="text-footnote text-ink2">{desc}</span>
            </span>
            {type === v && <Icon name="check" className="size-5 text-accent" />}
          </button>
        ))}
      </div>
      <div className="mb-2 mt-5 px-1 text-footnote font-semibold text-ink2">내용</div>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={5} maxLength={2000} placeholder="예: 다음 주 김장 체험에 앞치마가 꼭 있어야 하나요?" className="w-full resize-none rounded-md border-[1.5px] border-line bg-card px-3 py-2.5 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
      {err && <p role="alert" className="mt-1.5 text-footnote font-medium text-danger">{err}</p>}
      <p className="mt-2 px-1 text-footnote text-ink2">선생님이 확인하기 전에는 답이 나가지 않아요.</p>
      <Dock>
        <PrimaryButton onClick={submit} loading={create.isPending}>보내기</PrimaryButton>
      </Dock>
    </div>
  );
}
