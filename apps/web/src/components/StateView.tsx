import { Buddy, SymbolMark } from "./Brand";
import { Button } from "./Button";
import { Icon } from "./Icon";

type Kind = "loading" | "empty" | "error" | "forbidden";
/** 배지 색도 브랜드 색: + 블루 · 체크 민트 · 다시 시도 라벤더→블루 · 자물쇠 네이비 */
const BADGE: Record<Exclude<Kind, "loading">, { cls: string; icon: string }> = {
  empty: { cls: "from-[#3D63F2] to-[#2440C8]", icon: "plus" },
  error: { cls: "from-[#A8A3F4] to-[#5562F0]", icon: "retry" },
  forbidden: { cls: "from-[#2A3B5C] to-[#0B1F3A]", icon: "lock" },
};

/**
 * 모든 화면의 4가지 상태. 학부모는 말풍선 친구, 교사·원장은 '온' 심볼 (고정).
 * 상태마다 모양 + 배지 + 움직임이 달라서 그림만 봐도 구분된다.
 */
export function StateView({
  kind,
  audience,
  title,
  sub,
  action,
}: {
  kind: Kind;
  audience: "parent" | "staff";
  title?: string;
  sub?: string;
  action?: { label: string; run: () => void; primary?: boolean };
}) {
  const staffBadge = kind === "empty" ? { cls: "from-[#5BE0BC] to-[#2FB58C]", icon: "approve" } : kind !== "loading" ? BADGE[kind] : null;
  const parentBadge = kind !== "loading" ? BADGE[kind] : null;
  const badge = audience === "parent" ? parentBadge : staffBadge;
  const mark =
    audience === "parent" ? (
      <span className={kind === "loading" ? "m-bob" : kind === "empty" ? "m-float" : kind === "error" ? "m-shake" : "m-tilt"}>
        <Buddy face={kind === "loading" ? "processing" : kind === "empty" ? "guide" : kind === "error" ? "sorry" : "check"} className="size-24" />
      </span>
    ) : (
      <span className={kind === "error" ? "m-shake" : ""}>
        <SymbolMark className="size-16" motion={kind === "loading" ? "scan" : kind === "forbidden" ? "closed" : "blink"} />
      </span>
    );
  return (
    <div className="grid w-full justify-items-center gap-2 px-6 py-12 text-center" role={kind === "error" ? "alert" : undefined}>
      <span className="relative mb-1 grid place-items-center">
        {mark}
        {badge && (
          <span className={`m-pop absolute -bottom-1 -right-1.5 grid size-7 place-items-center rounded-full bg-gradient-to-br text-[15px] text-white ring-[3px] ring-g ${badge.cls}`}>
            <Icon name={badge.icon} />
          </span>
        )}
      </span>
      {kind === "loading" && audience === "parent" && (
        <span className="flex gap-1.5" aria-label="불러오는 중">
          {[0, 1, 2].map((i) => (
            <i key={i} className="m-dot size-[7px] rounded-full bg-accent" style={{ animationDelay: `${i * 0.15}s` }} />
          ))}
        </span>
      )}
      {title && <b className="text-body font-bold tracking-tight">{title}</b>}
      {sub && <p className="text-sub text-ink2">{sub}</p>}
      {action && (
        <Button variant={action.primary ? "primary" : "tinted"} className="mt-2 w-full max-w-[260px]" onClick={action.run}>
          {action.label}
        </Button>
      )}
    </div>
  );
}

export function SkeletonRows({ n = 5 }: { n?: number }) {
  return (
    <div className="grid gap-2 p-3" aria-hidden>
      {Array.from({ length: n }, (_, i) => (
        <div key={i} className="skel h-[60px] rounded-xl" />
      ))}
    </div>
  );
}
