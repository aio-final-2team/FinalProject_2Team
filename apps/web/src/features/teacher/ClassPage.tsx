import { ScreenTop } from "@/components/ScreenTop";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useNotes } from "@/api/notes";
import { useSession } from "@/app/session";
import { Icon } from "@/components/Icon";
import { QueryState } from "@/components/QueryState";
import { dateLabel, todayKST } from "@/domain/notes";

type Doc = { id: string; title: string; doc_type: string; status: string; effective_from: string; effective_to: string | null; classroom_ids: string[] };

/** 오늘 우리 반: 이번 달 식단표와 가정통신문 (API 28·30 자료). 자료 본문은 API가 주지 않아 제목·적용일·오늘 식단 줄만 보여 준다. */
export function ClassPage() {
  const { user } = useSession();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const notes = useNotes(cid, date);
  const docs = useQuery({ queryKey: ["documents"], queryFn: () => api<{ items: Doc[] }>("/api/v1/documents?size=50").then((r) => r.items) });
  const active = (type: string) => (docs.data ?? []).filter((d) => d.doc_type === type && d.status === "active");
  const menus = active("menu");
  const notices = active("notice");
  const meal = notes.data?.[0]?.content.items.find((i) => i.key === "meal");

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10 pt-2">
      <ScreenTop back={{ to: "/teacher/home", label: "홈" }} title="오늘 우리 반" sub={`${dateLabel(date)} · 식단표와 가정통신문을 모아 봤어요`} />

      <QueryState queries={[docs]} skeleton={2}>
        <Group title="식단표" empty="등록된 식단표가 없어요" count={menus.length + (meal ? 1 : 0)}>
          {meal && (
            <li className="px-3 py-3">
              <span className="text-caption font-bold text-accent-ink">오늘 식단</span>
              <b className="mt-0.5 block text-callout">{meal.value}</b>
              <span className="text-caption text-ink2">{meal.source.document_title ?? "식단표"}에서 가져왔어요</span>
            </li>
          )}
          {menus.map((d) => <DocRow key={d.id} d={d} />)}
        </Group>
        <Group title="가정통신문" empty="등록된 가정통신문이 없어요" count={notices.length}>
          {notices.map((d) => <DocRow key={d.id} d={d} />)}
        </Group>
      </QueryState>
      <p className="mt-5 px-1 text-caption text-ink2">자료 본문 보기는 서버가 자료 내용을 내려 주면 열려요. 지금은 제목과 적용일까지 보여요.</p>
    </div>
  );
}

function Group({ title, empty, count, children }: { title: string; empty: string; count: number; children: React.ReactNode }) {
  return (
    <section className="mt-5">
      <h2 className="mb-2 px-1 text-footnote font-semibold text-ink2">{title}</h2>
      {count > 0 ? <ul className="overflow-hidden rounded-lg bg-card shadow-card [&>li+li]:border-t [&>li+li]:border-sep">{children}</ul> : <p className="rounded-lg bg-card p-4 text-center text-callout text-ink2 shadow-card">{empty}</p>}
    </section>
  );
}

function DocRow({ d }: { d: Doc }) {
  return (
    <li className="flex items-center gap-3 px-3 py-3">
      <span className="grid size-9 shrink-0 place-items-center rounded-md bg-fill"><Icon name="document" className="size-5" /></span>
      <span className="min-w-0 flex-1">
        <b className="block truncate text-callout">{d.title}</b>
        <span className="text-caption text-ink2">{d.effective_from}부터{d.effective_to ? ` ${d.effective_to}까지` : ""}</span>
      </span>
    </li>
  );
}
