import { Link, useNavigate } from "react-router";
import { useCards } from "@/api/cards";
import { useCareRequests } from "@/api/care";
import { useChildren, useNotes } from "@/api/notes";
import { useSession } from "@/app/session";
import { ScreenTop } from "@/components/ScreenTop";
import { SubButton } from "@/components/Dock";
import { BellLink } from "@/components/BellLink";
import { Icon } from "@/components/Icon";
import { dateLabel, todayKST } from "@/domain/notes";
import { useRecords } from "@/features/records/store";
import { QueryState } from "@/components/QueryState";
import { SOON } from "./SoonPage";
import { TodayClass } from "./TodayClass";

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
  const care = useCareRequests(cid);
  const careOpen = (care.data ?? []).filter((c) => c.status !== "completed").length;

  const urgent = (inbox.data?.items ?? []).filter((c) => c.risk === "urgent");
  const list = notes.data ?? [];
  const recorded = (kids.data ?? []).filter((k) => records[k.id]?.length).length;
  const c = { needs_check: 0, draft: 0, ready: 0, sent: 0 };
  list.forEach((n) => c[n.status]++);
  const allSent = list.length > 0 && c.sent === list.length;
  const allReady = list.length > 0 && c.ready === list.length;
  // TODO(#368): 반·담임 표시 이름 API가 오면 실제 값으로 교체한다.
  const homeTitle = "별빛반 손영민 선생님";

  const noteState = !list.length
    ? { title: "오늘 알림장을 아직 만들지 않았어요", sub: recorded ? `관찰 기록 ${recorded}명의 내용을 반영할 수 있어요` : "오늘 함께한 활동부터 적으면 돼요", action: "알림장 만들기" }
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
      <ScreenTop title={homeTitle} sub={dateLabel(date)} right={<BellLink to="/teacher/notifications" />} />

      <QueryState queries={[kids, notes, inbox]} skeleton={3}>
      <TodayClass />
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
      <Label>오늘 알림장</Label>
      <Card accent>
        <span className={`inline-flex rounded-full px-2.5 py-1 text-caption font-bold ${allSent ? "bg-ok-tint text-ok" : "bg-tint text-accent-ink"}`}>오늘 알림장</span>
        <h2 className="mt-2 text-headline font-bold">{noteState.title}</h2>
        <p className="mt-1.5 text-footnote leading-relaxed text-ink2">{noteState.sub}</p>
        <SubButton className="mt-3 w-full rounded-lg" onClick={() => nav("/teacher/notes?tab=notes")}>{noteState.action}</SubButton>
      </Card>

      <Label>오늘 살펴볼 것</Label>
      <NavList>
        <NavRow to="/teacher/inbox" icon="inbox" title={`받은함 ${inbox.data?.counts.review ?? 0}건`} sub="보호자가 보낸 이야기를 살펴봐요" count={inbox.data?.counts.review ?? 0} />
        <NavRow to="/teacher/care" icon="medication" title={careOpen ? `귀가·투약 ${careOpen}건` : "귀가·투약"} sub={careOpen ? "오늘의 귀가와 투약 약속을 확인해요" : "오늘은 확인할 요청이 없어요"} count={careOpen} />
        <NavRow to="/teacher/notes?tab=records" icon="class" title="관찰 기록" sub={`오늘 ${recorded}명의 순간을 남겼어요 · 필요한 아이만 적어도 돼요`} />
      </NavList>

      <Label>더 보기</Label>
      <NavList>
        <NavRow to="/teacher/feed" icon="class" title="원 소식과 앨범" sub="원에 올라온 이야기와 사진을 볼 수 있어요" />
        <NavRow to="/teacher/calendar" icon="class" title="원 일정" sub="원 자료에 적힌 앞으로의 일정을 봐요" />
        <NavRow to="/teacher/busy" icon="hourglass" title="바쁜 시간" sub="상담을 받을 수 없는 시간을 정해요" />
        <NavRow to="/teacher/ask" icon="ai" title="AI에게 묻기" sub="원 자료를 보고 궁금한 점에 답해요" />
        <NavRow to="/teacher/class-consents" icon="document" title="보호자 동의 현황" sub="아이별로 필수 동의를 확인해요" />
        <NavRow to="/teacher/memory" icon="memory" title="내 AI 기억" sub="내가 거절한 이유를 보고 지울 수 있어요" />
        {Object.entries(SOON).map(([k, v]) => (
          <NavRow key={k} to={`/teacher/soon/${k}`} icon={v.icon} title={v.title} sub={v.sub} soon />
        ))}
      </NavList>

      </QueryState>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="mb-2.5 mt-6 px-1 text-callout font-bold text-ink">{children}</div>;
}

function Card({ children, accent }: { children: React.ReactNode; accent?: boolean }) {
  return <section className={`rounded-xl bg-card p-4 ${accent ? "border-[1.5px] border-accent shadow-card" : "shadow-card"}`}>{children}</section>;
}

/** 이동 행 묶음. 행 전체가 눌리고 높이 60 이상이라 손가락으로 누르기 쉽다 */
function NavList({ children }: { children: React.ReactNode }) {
  return <ul className="overflow-hidden rounded-xl bg-card shadow-card">{children}</ul>;
}

function NavRow({ to, icon, title, sub, count = 0, soon = false }: { to: string; icon: string; title: string; sub: string; count?: number; soon?: boolean }) {
  return (
    <li className="[&+&]:border-t [&+&]:border-sep">
      <Link to={to} className="flex min-h-[68px] items-center gap-3 px-3.5 py-3 transition-[transform,background-color] duration-100 active:scale-[.99] active:bg-fill">
        <span className="grid size-10 shrink-0 place-items-center rounded-lg bg-tint text-accent-ink"><Icon name={icon} className="size-5" /></span>
        <span className="min-w-0 flex-1">
          <b className="block truncate text-callout">{title}</b>
          <span className="block truncate text-footnote text-ink2">{sub}</span>
        </span>
        {count > 0 && <span className="grid h-6 min-w-6 place-items-center rounded-full bg-accent px-1.5 text-caption font-bold text-on-accent">{count}</span>}
        {soon && <span className="text-caption font-semibold text-ink2">준비 중</span>}
        <Icon name="chevR" className="size-4 shrink-0 text-ink2" />
      </Link>
    </li>
  );
}
