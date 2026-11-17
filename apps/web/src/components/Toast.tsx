import { AnimatePresence, animate, motion, useMotionValue, useReducedMotion } from "motion/react";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import type { Role } from "@/domain/types";
import { Buddy, SymbolMark } from "./Brand";
import { Icon } from "./Icon";

type Kind = "ok" | "undo" | "error";
type ToastInput = { kind: Kind; title: string; sub?: string; action?: { label: string; run: () => void }; ms?: number };
type ToastState = ToastInput & { id: number };

const Ctx = createContext<(t: ToastInput) => void>(() => {});
export const useToast = () => useContext(Ctx);

const DEFAULT_MS: Record<Kind, number> = { ok: 3000, undo: 5000, error: 0 };
const BADGE: Record<Kind, { cls: string; icon: string }> = {
  ok: { cls: "from-[#5BE0BC] to-[#2FB58C]", icon: "approve" },
  undo: { cls: "from-[#3D63F2] to-[#2440C8]", icon: "pending" },
  error: { cls: "from-[#A8A3F4] to-[#5562F0]", icon: "retry" },
};

/**
 * 토스트는 한 번에 하나. 위에서 내려오고, 위로 밀면 닫힌다. 손을 대고 있는 동안은 사라지지 않는다.
 * 아래 막대는 남은 시간. 실패는 직접 닫거나 다시 시도할 때까지 남는다.
 * 왼쪽 마크: 학부모 = 말풍선 친구, 교사·원장 = '온' 심볼 + 상태 배지.
 */
export function ToastProvider({ role, children }: { role: Role; children: ReactNode }) {
  const [t, setT] = useState<ToastState | null>(null);
  const show = useCallback((x: ToastInput) => setT({ ...x, id: Date.now() }), []);
  return (
    <Ctx.Provider value={show}>
      {children}
      <div className="pointer-events-none fixed inset-x-0 top-[max(12px,env(safe-area-inset-top))] z-[60] flex justify-center px-3" role="status" aria-live="polite">
        <AnimatePresence mode="wait">{t && <ToastView key={t.id} t={t} role={role} onDone={() => setT(null)} />}</AnimatePresence>
      </div>
    </Ctx.Provider>
  );
}

function ToastView({ t, role, onDone }: { t: ToastState; role: Role; onDone: () => void }) {
  const reduce = useReducedMotion();
  const ms = t.ms ?? DEFAULT_MS[t.kind];
  const progress = useMotionValue(1);
  const [left, setLeft] = useState(Math.ceil(ms / 1000));
  const ctrl = useRef<ReturnType<typeof animate> | null>(null);

  useEffect(() => {
    if (!ms) return;
    ctrl.current = animate(progress, 0, { duration: ms / 1000, ease: "linear", onComplete: onDone });
    const unsub = progress.on("change", (v) => setLeft(Math.max(0, Math.ceil((v * ms) / 1000))));
    return () => {
      ctrl.current?.stop();
      unsub();
    };
  }, [ms, progress, onDone]);

  const b = BADGE[t.kind];
  return (
    <motion.div
      className="glass pointer-events-auto relative flex w-full max-w-[420px] cursor-grab touch-none select-none items-center gap-3 overflow-hidden rounded-[18px] bg-bar px-3.5 pb-3.5 pt-3 shadow-[0_10px_30px_rgba(11,31,58,.2),0_0_0_.5px_var(--sep)] backdrop-blur-xl backdrop-saturate-[1.8]"
      initial={reduce ? { opacity: 0 } : { y: -120 }}
      animate={reduce ? { opacity: 1 } : { y: 0 }}
      exit={reduce ? { opacity: 0 } : { y: -140, transition: { duration: 0.28, ease: [0.4, 0, 1, 1] } }}
      transition={{ type: "spring", bounce: 0.15, duration: 0.5 }}
      drag="y"
      dragConstraints={{ top: 0, bottom: 0 }}
      dragElastic={{ top: 1, bottom: 0.15 }}
      onDragStart={() => ctrl.current?.pause()}
      onDragEnd={(_, i) => {
        if (i.offset.y < -28 || i.velocity.y < -350) onDone();
        else ctrl.current?.play();
      }}
    >
      <span className="relative grid size-9 shrink-0 place-items-center">
        {role === "parent" ? (
          <Buddy face={t.kind === "error" ? "sorry" : "done"} className="size-9" />
        ) : (
          <>
            <SymbolMark className="size-8" />
            <span className={`absolute -bottom-0.5 -right-1 grid size-4 place-items-center rounded-full bg-gradient-to-br text-[9px] text-white ring-2 ring-card ${b.cls}`}>
              <Icon name={b.icon} />
            </span>
          </>
        )}
      </span>
      <span className="grid min-w-0 flex-1">
        <b className="text-[14px]">{t.title}</b>
        {t.sub && <span className="text-[12px] text-ink2">{t.sub}</span>}
      </span>
      {t.action && (
        <button
          className={`shrink-0 px-1 py-1.5 text-[13px] font-bold tabular-nums ${t.kind === "error" ? "text-danger" : "text-accent"}`}
          onPointerDown={(e) => e.stopPropagation()}
          onClick={() => {
            t.action!.run();
            if (t.kind !== "error") onDone();
          }}
        >
          {t.action.label}
          {t.kind === "undo" ? ` ${left}` : ""}
        </button>
      )}
      {ms > 0 && (
        <span className="absolute inset-x-3.5 bottom-1.5 h-[3px] overflow-hidden rounded-full bg-fill2">
          <motion.span className="block h-full origin-left bg-accent" style={{ scaleX: progress }} />
        </span>
      )}
    </motion.div>
  );
}
