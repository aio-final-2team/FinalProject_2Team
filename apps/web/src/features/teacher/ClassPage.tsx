import { ScreenTop } from "@/components/ScreenTop";
import { Link } from "react-router";
import { useState } from "react";
import { useDocuments, type Doc } from "@/api/documents";
import { useNotes } from "@/api/notes";
import { useSession } from "@/app/session";
import { Icon } from "@/components/Icon";
import { QueryState } from "@/components/QueryState";
import { dateLabel, todayKST } from "@/domain/notes";


/** 오늘 우리 반: 이번 달 식단표와 가정통신문 (API 28·30 자료). 자료 본문은 API가 주지 않아 제목·적용일·오늘 식단 줄만 보여 준다. */
export function ClassPage() {
  const { user } = useSession();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const notes = useNotes(cid, date);
  const docs = useDocuments();
  const active = (type: string) => (docs.data ?? []).filter((d) => d.doc_type === type && d.status === "active").sort((a, b) => b.effective_from.localeCompare(a.effective_from));
  const menus = active("menu");
  const notices = active("notice");
  const [moreMenu, setMoreMenu] = useState(false);
  const [moreNotice, setMoreNotice] = useState(false);
  const FOLD = 4;
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
          {(moreMenu ? menus : menus.slice(0, FOLD)).map((d) => <DocRow key={d.id} d={d} />)}
          {menus.length > FOLD && <li><button type="button" onClick={() => setMoreMenu((v) => !v)} className="h-11 w-full text-footnote font-semibold text-accent-ink">{moreMenu ? "접기" : `${menus.length - FOLD}개 더 보기`}</button></li>}
        </Group>
        <Group title="가정통신문" empty="등록된 가정통신문이 없어요" count={notices.length}>
          {(moreNotice ? notices : notices.slice(0, FOLD)).map((d) => <DocRow key={d.id} d={d} />)}
          {notices.length > FOLD && <li><button type="button" onClick={() => setMoreNotice((v) => !v)} className="h-11 w-full text-footnote font-semibold text-accent-ink">{moreNotice ? "접기" : `${notices.length - FOLD}개 더 보기`}</button></li>}
        </Group>
      </QueryState>
      
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
    <li>
      <Link to={`/teacher/class/${d.id}`} className="flex items-center gap-3 px-3 py-3 active:bg-fill">
        <span className="grid size-9 shrink-0 place-items-center rounded-md bg-fill"><Icon name="document" className="size-5" /></span>
        <span className="min-w-0 flex-1">
          <b className="block truncate text-callout">{d.title}</b>
          <span className="text-caption text-ink2">{d.effective_from}부터{d.effective_to ? ` ${d.effective_to}까지` : ""}</span>
        </span>
        <Icon name="chevR" className="size-4 shrink-0 text-ink2" />
      </Link>
    </li>
  );
}
