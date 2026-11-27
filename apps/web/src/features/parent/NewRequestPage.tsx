import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError } from "@/api/client";
import { useCreateRequest, usePickupGuardians, type CareInput, type RequestType } from "@/api/requests";
import { Dock, PrimaryButton } from "@/components/Dock";
import { Icon } from "@/components/Icon";
import { ScreenTop } from "@/components/ScreenTop";

const TYPES: [RequestType, string, string][] = [
  ["inquiry", "문의", "궁금한 점을 물어봐요"],
  ["consultation", "상담", "선생님과 상담 시간을 잡아요"],
  ["complaint", "민원", "불편하거나 걱정되는 점을 알려요"],
  ["medication", "투약", "약을 먹여 달라고 부탁해요"],
  ["pickup", "귀가", "오늘 누가 데리러 가는지 알려요"],
];

/** 투약·귀가는 칸을 나눠 받는다. 비워도 보낼 수 있고, 빠진 칸은 선생님이 다시 물어봐요 */
const CARE_FIELDS: Partial<Record<RequestType, { key: keyof CareInput; label: string; placeholder: string }[]>> = {
  medication: [
    { key: "medication_name", label: "약 이름", placeholder: "예: 해열 시럽" },
    { key: "medication_dose", label: "먹일 양", placeholder: "예: 2.5ml" },
    { key: "medication_time", label: "먹일 시간", placeholder: "예: 점심 식사 후" },
  ],
  pickup: [
    { key: "pickup_name", label: "데리러 오는 분 이름", placeholder: "예: 김미영" },
    { key: "pickup_relation", label: "아이와의 관계", placeholder: "예: 이모" },
  ],
};

/* 쓰던 요청을 이 기기에 임시 저장한다. 다른 화면에 다녀와도 남고, 보내면 지운다 (서버에 임시 저장 API가 없다) */
const DRAFT_KEY = "yuchion.newRequest";
type Draft = { type: RequestType; body: string; care: CareInput };
const loadDraft = (): Draft | null => {
  try {
    const v = JSON.parse(localStorage.getItem(DRAFT_KEY) ?? "null");
    return v && typeof v.body === "string" && TYPES.some((t) => t[0] === v.type) ? { type: v.type, body: v.body, care: v.care ?? {} } : null;
  } catch {
    return null;
  }
};

/** P-03 새 요청 쓰기. 문의·상담·민원·투약·귀가 */
export function NewRequestPage() {
  const nav = useNavigate();
  const me = useQuery({ queryKey: ["me"], queryFn: () => api<{ children: { id: string; display_name: string }[] }>("/api/v1/me") });
  const create = useCreateRequest();
  const saved = useMemo(loadDraft, []);
  const [type, setType] = useState<RequestType>(saved?.type ?? "inquiry");
  const [body, setBody] = useState(saved?.body ?? "");
  const [care, setCare] = useState<CareInput>(saved?.care ?? {});
  const sent = useRef(false);
  const hasText = !!body.trim() || Object.values(care).some((v) => String(v ?? "").trim());
  useEffect(() => {
    if (sent.current) return;
    try {
      if (hasText) localStorage.setItem(DRAFT_KEY, JSON.stringify({ type, body, care }));
      else localStorage.removeItem(DRAFT_KEY);
    } catch {
      /* 저장이 막혀도 이번 화면에서는 계속 쓸 수 있다 */
    }
  }, [type, body, care, hasText]);
    const [err, setErr] = useState("");
  const child = me.data?.children[0]?.id; /* 아이가 여럿이면 고르는 칸을 더한다. 시연 계정은 한 명 */
  const guardians = usePickupGuardians(type === "pickup" ? child : undefined).data ?? [];

  const submit = () => {
    if (!body.trim()) return setErr("어떤 내용인지 한 줄 이상 적어 주세요.");
    if (!child) return setErr("아이 정보를 불러오지 못했어요. 잠시 뒤 다시 눌러 주세요.");
    setErr("");
    create.mutate(
      { type, body: body.trim(), child_id: child, ...Object.fromEntries(Object.entries(care).filter(([k, v]) => (CARE_FIELDS[type]?.some((f) => f.key === k) || (type === "pickup" && k === "pickup_guardian_id")) && String(v ?? "").trim()).map(([k, v]) => [k, String(v).trim()])) },
      { onSuccess: (r) => { sent.current = true; try { localStorage.removeItem(DRAFT_KEY); } catch { /* 무시 */ } nav(`/parent/requests/${r.request.id}`, { replace: true }); }, onError: (e) => setErr(e instanceof ApiError ? e.message : "보내지 못했어요. 잠시 뒤 다시 눌러 주세요.") },
    );
  };

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-48">
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
      {type === "pickup" && guardians.length > 0 && (
        <div className="mt-5 grid gap-2">
          <div className="px-1 text-footnote font-semibold text-ink2">등록된 인계자 <span className="font-normal">(등록되지 않은 분이 오시면 선생님이 한 번 더 확인해요)</span></div>
          <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="등록된 인계자">
            {guardians.map((g) => (
              <button key={g.id} type="button" role="radio" aria-checked={care.pickup_guardian_id === g.id} onClick={() => setCare((c) => ({ ...c, pickup_guardian_id: g.id, pickup_name: g.display_name }))} className={`h-11 rounded-full px-4 text-callout font-semibold ${care.pickup_guardian_id === g.id ? "bg-brand-fill text-on-brand" : "bg-card text-ink shadow-card"}`}>
                {g.display_name}
              </button>
            ))}
            <button type="button" role="radio" aria-checked={!care.pickup_guardian_id} onClick={() => setCare((c) => ({ ...c, pickup_guardian_id: undefined, pickup_name: c.pickup_guardian_id ? "" : c.pickup_name }))} className={`h-11 rounded-full px-4 text-callout font-semibold ${!care.pickup_guardian_id ? "bg-brand-fill text-on-brand" : "bg-card text-ink shadow-card"}`}>
              다른 분이 와요
            </button>
          </div>
        </div>
      )}
      {CARE_FIELDS[type] && (
        <div className="mt-5 grid gap-3">
          <div className="px-1 text-footnote font-semibold text-ink2">자세한 내용 <span className="font-normal">(비워도 보낼 수 있어요. 빠진 건 선생님이 다시 물어봐요)</span></div>
          {CARE_FIELDS[type]!.map((f) => (
            <label key={f.key} className="grid gap-1.5">
              <span className="px-1 text-footnote font-semibold">{f.label}</span>
              <input value={care[f.key] ?? ""} readOnly={f.key === "pickup_name" && !!care.pickup_guardian_id} onChange={(e) => setCare((c) => ({ ...c, [f.key]: e.target.value }))} maxLength={100} placeholder={f.placeholder} className="h-12 rounded-md border-[1.5px] border-line bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
            </label>
          ))}
        </div>
      )}
      <div className="mb-2 mt-5 px-1 text-footnote font-semibold text-ink2">내용</div>
      <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={5} maxLength={2000} placeholder={type === "medication" ? "예: 점심 먹고 시럽 2.5ml 먹여 주세요" : type === "pickup" ? "예: 오늘은 이모가 데리러 가요" : "예: 다음 주 김장 체험에 앞치마가 꼭 있어야 하나요?"} className="w-full resize-none rounded-md border-[1.5px] border-line bg-card px-3 py-2.5 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]" />
      {err && <p role="alert" className="mt-1.5 text-footnote font-medium text-danger">{err}</p>}
      {hasText && <p className="mt-1.5 px-1 text-caption text-ink2">적은 내용은 이 기기에 임시 저장돼요</p>}
      <p className="mt-2 px-1 text-footnote text-ink2">선생님이 확인하기 전에는 답이 나가지 않아요.</p>
      <Dock>
        <PrimaryButton onClick={submit} loading={create.isPending}>보내기</PrimaryButton>
      </Dock>
    </div>
  );
}
