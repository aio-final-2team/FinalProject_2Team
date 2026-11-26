import { useParams } from "react-router";
import { TYPE_LABEL, useAiAnswered, useRequest } from "@/api/requests";
import { ScreenTop } from "@/components/ScreenTop";
import { SkeletonRows, StateView } from "@/components/StateView";
import { fmtDateTime } from "@/domain/datetime";
import type { Role } from "@/domain/types";

/** AI가 카드 없이 바로 답하고 끝낸 요청을 읽기만 하는 화면(API GET /requests/{id}) */
export function AiAnsweredPage({ role }: { role: Role }) {
  const { requestId } = useParams();
  const list = useAiAnswered(true);
  const item = list.data?.find((r) => r.id === requestId);
  const detail = useRequest(requestId);
  const d = detail.data;
  const who = [item?.child_name, item?.requester_name].filter(Boolean).join(" · ");
  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop back={{ to: `/${role}/inbox`, label: "받은함" }} title="바로 안내한 요청" />
      {detail.isLoading && <SkeletonRows />}
      {detail.isError && <StateView kind="error" audience="staff" title="요청을 불러오지 못했어요" sub="잠시 뒤 다시 열어 주세요" />}
      {d && (
        <div className="mt-3 grid gap-4">
          <header className="grid gap-1">
            <h2 className="text-headline font-bold tracking-[-0.02em]">{d.request.title ?? TYPE_LABEL[d.request.type]}</h2>
            <p className="text-sub text-ink2">{[TYPE_LABEL[d.request.type], who, fmtDateTime(d.request.created_at)].filter(Boolean).join(" · ")}</p>
          </header>
          <p className="rounded-2xl bg-tint px-4 py-3 text-callout text-accent-ink">
            담당 범위 밖 문의라서 정해진 문구로 바로 안내했어요. 카드는 만들어지지 않았고, 따로 할 일은 없어요.
          </p>
          <ul className="grid gap-2" aria-label="주고받은 글">
            {d.messages.map((m) => {
              const mine = m.sender_role === "parent";
              return (
                <li key={m.id} className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-callout ${mine ? "bg-card" : "ml-auto bg-tint text-accent-ink"}`}>
                  <span className="mb-0.5 block text-caption font-semibold opacity-70">{mine ? "학부모" : m.sender_type === "agent" ? "바로 안내 · 정해진 문구" : m.sender_type === "system" ? "시스템" : "교직원"}</span>
                  <span className="whitespace-pre-line break-keep">{m.body}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
