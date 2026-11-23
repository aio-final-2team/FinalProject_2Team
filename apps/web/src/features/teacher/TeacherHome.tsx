import { Link, useNavigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useCards } from "@/api/cards";
import { api } from "@/api/client";
import { useChildren, useNotes } from "@/api/notes";
import { useSession } from "@/app/session";
import { SymbolMark } from "@/components/Brand";
import { PrimaryButton, SubButton } from "@/components/Dock";
import { BellLink } from "@/components/BellLink";
import { Icon } from "@/components/Icon";
import { dateLabel, todayKST } from "@/domain/notes";
import { useRecords } from "@/features/records/store";
import { QueryState } from "@/components/QueryState";
import { SOON } from "./SoonPage";

type Doc = { id: string; title: string; doc_type: string; status: string; effective_from: string };

/** 홈은 입력 화면이 아니라 API 상태를 요약하고 다음 행동 하나를 안내한다. */
export function TeacherHome() {
  const { user } = useSession();
  const nav = useNavigate();
  const cid = user?.classroom_ids[0];
  const date = todayKST();
  const kids = useChildren(cid);
  const notes = useNotes(cid, date);
  const inbox = useCards("review");
  const { records } = useRecords(cid, date);
  const docs = useQuery({ queryKey: ["documents"], queryFn: () => api<{ items: Doc[] }>("/api/v1/documents?size=50").then((r) => r.items) });

  const urgent = (inbox.data?.items ?? []).filter((c) => c.risk === "urgent");
  const list = notes.data ?? [];
  const recorded = (kids.data ?? []).filter((k) => records[k.id]?.length).length;
  const c = { needs_check: 0, draft: 0, ready: 0, sent: 0 };
  list.forEach((n) => c[n.status]++);
  const allSent = list.length > 0 && c.sent === list.length;
  const allReady = list.length > 0 && c.ready === list.length;
  const meal = list[0]?.content.items.find((i) => i.key === "meal");
  const menuDoc = docs.data?.find((d) => d.doc_type === "menu" && d.status === "active");
  const notice = docs.data?.find((d) => d.doc_type === "notice" && d.status === "active");

  const noteState = !list.length
    ? { title: "오늘 알림장을 아직 만들지 않았어요", sub: recorded ? `관찰 기록 ${recorded}명의 내용을 반영할 수 있어요` : "오늘 함께한 활동부터 적으면 돼요", action: "알림장 작성 시작" }
    : allSent
      ? { title: `${c.sent}가정에 알림장을 보냈어요`, sub: "보낸 내용은 알림장에서 다시 볼 수 있어요", action: "보낸 알림장 보기" }
      : c.needs_check
        ? { title: `먼저 확인할 알림장 ${c.needs_check}개`, sub: "표시된 내용만 확인하면 돼요", action: `${c.needs_check}명 확인하기` }
        : c.draft
          ? { title: `문제없이 작성된 알림장 ${c.draft}개`, sub: "한 번에 확인할 수 있어요", action: "초안 확인하기" }
          : allReady
            ? { title: `${list.length}명에게 보낼 준비가 끝났어요`, sub: "마지막으로 받는 사람을 확인해 주세요", action: "알림장 보내기" }
            : { title: "알림장을 확인하고 있어요", sub: `확인 완료 ${c.ready}명`, action: "계속 확인하기" };

  return (
    <div className="mx-auto max-w-[680px] px-4 pb-32 lg:pb-10">
      <header className="flex min-h-[52px] items-center justify-between pt-2">
        <SymbolMark className="size-8" />
        <BellLink to="/teacher/notifications" />
      </header>
      <h1 className="mt-1 text-large-title font-bold tracking-[-0.025em]">오늘</h1>
      <p className="mt-0.5 text-footnote font-medium text-ink2">{dateLabel(date)} · {user?.display_name}</p>

      <QueryState queries={[kids, notes, inbox]} skeleton={3}>
      {urgent.length > 0 && (
        <>
          <Label>먼저 확인해 주세요</Label>
          <section className="rounded-lg bg-ink p-3 text-card">
            <span className="text-caption font-bold">긴급</span>
            <h2 className="mt-1 text-headline font-bold">아이 안전과 관련된 요청 {urgent.length}건이 있어요</h2>
            <p className="mt-1 text-footnote opacity-90">{[...new Set(urgent.map((c) => c.urgentReason).filter(Boolean))].join(" · ") || "원장님께도 함께 보고됐어요"}</p>
            <button type="button" onClick={() => nav(`/teacher/inbox/${urgent[0].id}`)} className="mt-3 flex h-[52px] w-full items-center justify-center rounded-md bg-card text-body font-semibold text-ink active:scale-[.97]">
              긴급 요청 확인하기
            </button>
          </section>
        </>
      )}
      <Label>다음 할 일</Label>
      <Card accent={!allSent}>
        <span className={`text-caption font-bold ${allSent ? "text-ok" : "text-accent-ink"}`}>오늘 알림장</span>
        <h2 className="mt-1 text-headline font-bold">{noteState.title}</h2>
        <p className="mt-1 text-footnote text-ink2">{noteState.sub}</p>
        <PrimaryButton className="mt-3 w-full" onClick={() => nav("/teacher/notes")}>{noteState.action}</PrimaryButton>
      </Card>

      <Label>확인할 요청</Label>
      <Card>
        <div className="flex items-center gap-3">
          <span className="grid size-10 shrink-0 place-items-center rounded-md bg-tint text-accent-ink"><Icon name="inbox" className="size-5" /></span>
          <span className="min-w-0 flex-1">
            <b className="block text-headline">{inbox.data?.counts.review ?? 0}건을 확인해 주세요</b>
            <span className="text-footnote text-ink2">답변·상담·민원 요청을 모아 봐요</span>
          </span>
          <SubButton small onClick={() => nav("/teacher/inbox")}>받은함 보기</SubButton>
        </div>
      </Card>

      <Label>관찰 기록</Label>
      <Card>
        <div className="flex items-center justify-between gap-3">
          <span>
            <b className="block text-headline">오늘 {recorded}명 기록</b>
            <span className="text-footnote text-ink2">필요한 아이만 짧게 남겨도 돼요</span>
          </span>
          <Link to="/teacher/records" className="inline-flex h-9 items-center rounded-md bg-fill px-3 text-footnote font-semibold">기록 추가</Link>
        </div>
      </Card>

      <Label>곧 만나요</Label>
      <ul className="overflow-hidden rounded-lg bg-card shadow-card">
        {Object.entries(SOON).map(([k, v]) => (
          <li key={k} className="border-b border-sep last:border-0">
            <Link to={`/teacher/soon/${k}`} className="flex min-h-12 items-center gap-3 px-3 py-2.5">
              <span className="grid size-9 shrink-0 place-items-center rounded-md bg-fill text-ink"><Icon name={v.icon} className="size-5" /></span>
              <span className="min-w-0 flex-1 text-callout font-semibold">{v.title}</span>
              <span className="text-caption font-semibold text-ink2">준비 중</span>
              <Icon name="chevR" className="size-4 text-ink2" />
            </Link>
          </li>
        ))}
      </ul>

      <Label>오늘 우리 반</Label>
      <div className="grid gap-2">
        <Card>
          <b className="block text-callout">{meal?.value ?? (menuDoc ? "오늘 식단은 알림장에 자동으로 들어가요" : "등록된 오늘 식단이 없어요")}</b>
          <span className="text-caption text-ink2">{meal?.source.document_title ?? menuDoc?.title ?? "식단표"}</span>
        </Card>
        {notice && <Card><b className="block text-callout">{notice.title}</b><span className="text-caption text-ink2">가정통신문 · {notice.effective_from}부터</span></Card>}
      </div>
      </QueryState>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mb-2 mt-5 px-1 text-footnote font-semibold text-ink2">{children}</div>;
}

function Card({ children, accent }: { children: React.ReactNode; accent?: boolean }) {
  return <section className={`rounded-lg bg-card p-3 ${accent ? "border-[1.5px] border-accent" : "shadow-card"}`}>{children}</section>;
}
