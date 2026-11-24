import { Link } from "react-router";
import { TYPE_LABEL, useMyRequests } from "@/api/requests";
import { Buddy } from "@/components/Brand";
import { Dock } from "@/components/Dock";
import { Icon } from "@/components/Icon";
import { QueryState } from "@/components/QueryState";
import { PrimaryLink } from "./parts";

/** P-02 요청 목록 (T21 뼈대). 상태 이름은 서버가 주는 status_label을 그대로 쓴다 (학부모용 표시 이름) */
export function RequestsPage() {
  const q = useMyRequests();
  const items = q.data?.items ?? [];
  return (
    <div className="px-4 pb-48">
      <h1 className="pt-4 text-large-title font-bold tracking-[-0.025em]">요청</h1>
      <p className="mb-4 mt-0.5 text-footnote font-medium text-ink2">보낸 문의·상담·민원이 어디까지 왔는지 볼 수 있어요</p>
      <QueryState queries={[q]} skeleton={3} errorTitle="요청을 불러오지 못했어요">
      {!items.length ? (
        <div className="grid justify-items-center gap-2 py-12 text-center">
          <Buddy face="waiting" className="size-20" />
          <b className="text-headline">아직 보낸 요청이 없어요</b>
          <p className="text-callout text-ink2">궁금한 점이 있으면 새 요청으로 물어보세요.</p>
        </div>
      ) : (
        <ul className="overflow-hidden rounded-lg bg-card shadow-card">
          {items.map((r) => (
            <li key={r.id} className="[&+&]:border-t [&+&]:border-sep">
              <Link to={`/parent/requests/${r.id}`} className="flex min-h-14 items-center gap-3 px-3 py-2.5">
                <span aria-hidden className="grid size-8 shrink-0 place-items-center rounded-sm bg-fill text-caption font-bold">{(TYPE_LABEL[r.type] ?? r.type).slice(0, 2)}</span>
                <span className="min-w-0 flex-1">
                  <b className="block truncate text-headline font-semibold">{r.title ?? "제목 없음"}</b>
                  <span className="flex gap-2 text-footnote">
                    <span className="font-bold text-lav">{r.status_label}</span>
                    {r.next_action && <span className="text-ink2">· {r.next_action}</span>}
                  </span>
                </span>
                <Icon name="chevR" className="size-4 text-ink2" />
              </Link>
            </li>
          ))}
        </ul>
      )}
      </QueryState>
      <Dock>
        <PrimaryLink to="/parent/requests/new">새 요청 쓰기</PrimaryLink>
      </Dock>
    </div>
  );
}
