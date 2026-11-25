import { Link, useParams, useSearchParams } from "react-router";
import { useCards, type TypeFilter } from "@/api/cards";
import { ScreenTop } from "@/components/ScreenTop";
import { dateLabel, todayKST } from "@/domain/notes";
import { BackLink as SharedBackLink } from "@/components/BackLink";
import { SkeletonRows, StateView } from "@/components/StateView";
import { Pill, WeightIcon } from "@/components/Tags";
import { INBOX_FILTERS, TYPE_LABEL, type InboxFilter } from "@/domain/status";
import { reviewRank, type Card, type Role } from "@/domain/types";
import { CardDetail } from "./CardDetail";

const EMPTY: Record<InboxFilter, string> = {
  review: "지금 확인할 카드가 없어요",
  judge: "판단이 필요한 민원이 없어요",
  unassigned: "담당을 정할 카드가 없어요",
  hold: "보류한 카드가 없어요",
  progress: "진행 중인 카드가 없어요",
  done: "완료한 카드가 없어요",
};

/** 카드 목록 응답에는 접수 시각이 없고 처리 기한(due_at)만 있다. 기한까지 남은 시간(지났으면 지난 시간)을 보여 준다 */
function ago(iso: string) {
  const m = Math.round((new Date(iso).getTime() - Date.now()) / 60000);
  const a = Math.abs(m);
  const unit = a < 60 ? `${a}분` : a < 60 * 24 ? `${Math.round(a / 60)}시간` : `${Math.round(a / 60 / 24)}일`;
  return m >= 0 ? `${unit} 남음` : `${unit} 지남`;
}

function weightOf(c: Card) {
  if (c.risk === "urgent") return "urgent" as const;
  if (c.status === "completed") return "done" as const;
  if (c.inboxFilter === "review" || c.inboxFilter === "judge") return "action" as const;
  return "normal" as const;
}

function Row({ c, active, to, role }: { c: Card; active: boolean; to: string; role: Exclude<Role, "parent"> }) {
  const w = weightOf(c);
  /* 제목은 한 번만 보여 준다. 접수 원문은 제목에 이미 담겨 있으면 다시 쓰지 않는다 */
  const norm = (t: string) => t.replace(/[\s"'“”.…]/g, "");
  const head = c.risk === "urgent" ? (c.urgentReason ?? c.title) : c.title;
  const showOriginal = !!c.original && !norm(c.original).startsWith(norm(c.title)) && !norm(c.title).startsWith(norm(c.original));
  const flags: { t: string; tone: "action" | "answered" | "done" | "wait" | "urgent" }[] = [];
  if (c.risk === "urgent") flags.push({ t: "초안 없음", tone: "urgent" });
  if (c.risk === "judge") flags.push({ t: "AI 판단 불확실", tone: "action" });
  if (c.repeatCount && c.repeatCount >= 3) flags.push({ t: `반복 ${c.repeatCount}번째`, tone: "action" });
  if (c.escalated) flags.push({ t: "원장 보고", tone: "wait" });
  if (c.parentConfirmedAt && c.status === "sent_or_booked") flags.push({ t: "처리 완료 대기", tone: "answered" });
  if (c.slots) flags.push({ t: `학부모가 ${c.slots.filter((s) => s.picked).length}개 고름`, tone: "wait" });
  if (c.groupedCount) flags.push({ t: `같은 질문 ${c.groupedCount}건`, tone: "wait" });
  return (
    <Link
      to={to}
      aria-current={active ? "page" : undefined}
      className={`flex gap-3 rounded-2xl px-3.5 py-3 transition-colors ${active ? "bg-tint" : "bg-card hover:bg-fill"}`}
    >
      <WeightIcon weight={w} icon={c.risk === "urgent" || c.risk === "judge" ? "urgent" : c.type} />
      <span className="grid min-w-0 flex-1 gap-0.5">
        <span className="flex items-baseline justify-between gap-2">
          <b className="text-[14.5px]">{head}</b>
          <span className="shrink-0 text-[12px] text-ink2 tabular-nums">{ago(c.createdAt)}</span>
        </span>
        <span className="text-[13px] text-ink2">
          {role === "director" && <span className="mr-1 font-semibold text-ink">{c.className} ·</span>}
          {c.risk === "judge" ? "판단 필요 · " : ""}{TYPE_LABEL[c.type]}
          {showOriginal && <> · "{c.original}"</>}
        </span>
        {flags.length > 0 && (
          <span className="mt-1 flex flex-wrap gap-1">
            {flags.map((f) => (
              <Pill key={f.t} tone={f.tone}>{f.t}</Pill>
            ))}
          </span>
        )}
      </span>
    </Link>
  );
}

/**
 * T-01 · D-01 받은함. 교사와 원장이 같은 화면을 쓴다.
 * 1024px 이상: 왼쪽 목록 + 오른쪽 카드 상세. 좁은 화면: 목록 → 상세로 이동.
 * 고른 필터는 주소(?filter=)에 남아 뒤로 가도 유지된다.
 */
export function InboxPage({ role }: { role: Exclude<Role, "parent"> }) {
  const { cardId } = useParams();
  const [params, setParams] = useSearchParams();
  const filter = (params.get("filter") as InboxFilter) || "review";
  const type = (params.get("type") as TypeFilter) || "all";
  const { data, isLoading, isError, refetch, dataUpdatedAt } = useCards(filter, type);
  const counts = data?.counts ?? Object.fromEntries(INBOX_FILTERS.map((f) => [f.key, 0]));
  const list = (data?.items ?? [])
    .sort((a, b) => (filter === "review" ? reviewRank(a) - reviewRank(b) : 0) || +new Date(a.createdAt) - +new Date(b.createdAt));
  const q = `?filter=${filter}${type === "all" ? "" : `&type=${type}`}`;
  const base = `/${role}/inbox`;

  const listPane = (
    <section className={`min-w-0 ${cardId ? "hidden lg:block" : ""}`} aria-label="받은함 목록">
      <div className="sticky top-0 z-10 bg-g/90 px-4 pb-3 backdrop-blur-xl lg:px-5 lg:pt-4">
        <ScreenTop
          title="받은함"
          sub={
            <>
              {role === "teacher" ? "우리 반" : "원 전체"} · {dateLabel(todayKST())}
              {role === "director" && counts.review > 0 && (
                <>
                  <br />원장 보고 <b className="text-ink">{data?.items.filter((c) => c.escalated).length ?? 0}건</b>을 먼저 봐 주세요
                </>
              )}
            </>
          }
        />
        <div className="-mx-4 mt-3 flex gap-1.5 overflow-x-auto px-4 [scrollbar-width:none] lg:mx-0 lg:flex-wrap lg:px-0" role="tablist" aria-label="받은함 필터">
          {INBOX_FILTERS.map((f) => (
            <button
              key={f.key}
              role="tab"
              aria-selected={filter === f.key}
              onClick={() => setParams({ filter: f.key })}
              className={`shrink-0 rounded-full px-3 py-1.5 text-[13px] font-medium transition-[transform,background] duration-200 active:scale-95 ${filter === f.key ? "bg-ink text-card" : "bg-card text-ink hover:bg-fill2"}`}
            >
              {f.label}
              <span className="ml-1 tabular-nums opacity-60">{counts[f.key]}</span>
            </button>
          ))}
        </div>
      </div>
      <div className="grid gap-2 px-3 pb-6 lg:px-4">
        {isLoading && <SkeletonRows />}
        {isError && (
          <StateView kind="error" audience="staff" title="카드를 불러오지 못했어요" sub={dataUpdatedAt ? `마지막으로 불러온 시각 ${new Date(dataUpdatedAt).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}` : "연결을 확인해 주세요"} action={{ label: "다시 시도", run: () => refetch() }} />
        )}
        {data && list.length === 0 && <StateView kind="empty" audience="staff" title={EMPTY[filter]} sub="새 카드가 오면 숫자로 알려 드려요" />}
        {list.map((c) => (
          <Row key={c.id} c={c} role={role} active={c.id === cardId} to={`${base}/${c.id}${q}`} />
        ))}
      </div>
    </section>
  );

  return (
    <div className="lg:grid lg:h-dvh lg:grid-cols-[minmax(360px,440px)_1fr]">
      <div className="lg:h-dvh lg:overflow-y-auto">{listPane}</div>
      <div className={`min-w-0 lg:h-dvh lg:overflow-y-auto lg:border-l lg:border-sep ${cardId ? "" : "hidden lg:block"}`}>
        {cardId ? (
          <CardDetail key={cardId} id={cardId} role={role} backTo={`${base}${q}`} />
        ) : (
          <div className="grid h-full place-items-center">
            <StateView kind="empty" audience="staff" title="왼쪽에서 카드를 골라 주세요" sub="긴급 카드가 맨 위에 있어요" />
          </div>
        )}
      </div>
    </div>
  );
}

export function BackLink({ to }: { to: string }) {
  return <SharedBackLink to={to} label="받은함" className="lg:hidden" />;
}
