import { Buddy, SymbolMark } from "./Brand";
import { Button } from "./Button";
import { Icon } from "./Icon";

type Kind = "loading" | "empty" | "error" | "forbidden";
/**
 * 오류 원인별 모양 (11/23 정함). 같은 오류 상태 안에서 마크 움직임·배지·학부모 표정을 원인마다 다르게 쓴다.
 * 새 그림은 없이 기존 '온' 심볼 움직임(blink·scan·closed)·배지 아이콘과 말풍선 친구 표정만 조합한다.
 */
export type Variant = "server" | "offline" | "timeout" | "forbidden" | "notfound" | "conflict";
type Motion = "blink" | "blink2" | "scan" | "scan2" | "closed";
type Face = "sorry" | "waiting" | "check";
/**
 * 마크 규칙 (11/24 정함)
 * - 모든 상태에 움직임이 있다: 눈 움직임(교사) 또는 몸 움직임(학부모)이 멈추지 않고 이어진다. 움직임 줄이기 설정이면 시스템이 멈춘다.
 * - 배지 색: 교사·원장은 전부 라벤더, 학부모는 전부 네이비. 배지 모양이 원인을 알려 준다.
 * - 학부모 표정: 기다리는 표정(waiting)·확인하는 표정(check)만 쓴다. 미안해하는 표정(sorry)은 서버 오류 전용, 안내하는 표정(guide)은 완료 때만 쓴다.
 */
const STAFF_BADGE = "from-[#A8A3F4] to-[#5562F0]";
const PARENT_BADGE = "from-[#2A3B5C] to-[#0B1F3A]";
/** once: 한 번 하는 움직임(흔들기·기울이기), loop: 계속 이어지는 움직임 */
const VARIANT: Record<Variant, { motion: Motion; icon: string; face: Face; once?: string; loop: string }> = {
  server: { motion: "blink2", icon: "retry", face: "sorry", once: "m-shake", loop: "m-float" },
  offline: { motion: "blink", icon: "wifi-off", face: "waiting", loop: "m-float" },
  timeout: { motion: "scan", icon: "hourglass", face: "waiting", loop: "m-bob" },
  forbidden: { motion: "closed", icon: "lock", face: "check", once: "m-tilt", loop: "m-sway" },
  notfound: { motion: "scan", icon: "search", face: "check", loop: "m-float" },
  conflict: { motion: "scan2", icon: "overlap", face: "check", loop: "m-float" },
};
/** variant 없이 쓰는 기본 상태 */
const KIND: Record<Exclude<Kind, "loading">, { motion: Motion; icon: string; face: Face; once?: string; loop: string }> = {
  empty: { motion: "blink", icon: "plus", face: "waiting", loop: "m-float" },
  error: VARIANT.server,
  forbidden: VARIANT.forbidden,
};

/**
 * 모든 화면의 4가지 상태. 학부모는 말풍선 친구, 교사·원장은 '온' 심볼 (고정).
 * 상태마다 모양 + 배지 + 움직임이 달라서 그림만 봐도 구분된다. 오류는 variant로 원인별 모양을 더 나눈다.
 */
export function StateView({
  kind,
  audience,
  title,
  sub,
  action,
  variant,
}: {
  kind: Kind;
  audience: "parent" | "staff";
  title?: string;
  sub?: string;
  action?: { label: string; run: () => void; primary?: boolean };
  variant?: Variant;
}) {
  const v = variant ? VARIANT[variant] : kind === "loading" ? undefined : KIND[kind];
  const badge = v ? { cls: audience === "parent" ? PARENT_BADGE : STAFF_BADGE, icon: v.icon } : null;
  /* 움직임은 두 겹: 바깥은 한 번 하는 움직임, 안쪽은 계속 이어지는 움직임 */
  const once = v?.once ?? "";
  const loop = v?.loop ?? "m-bob";
  const mark =
    audience === "parent" ? (
      <span className={once}>
        <span className={`inline-block ${loop}`}>
          <Buddy face={v ? v.face : "processing"} className="size-24" />
        </span>
      </span>
    ) : (
      <span className={once}>
        <span className={`inline-block ${v ? loop : ""}`}>
          <SymbolMark className="size-16" motion={v ? v.motion : "scan"} />
        </span>
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
      {title && <b className="text-balance break-keep text-body font-bold tracking-tight">{title}</b>}
      {sub && <p className="max-w-[300px] whitespace-pre-line text-pretty break-keep text-sub text-ink2">{sub}</p>}
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
