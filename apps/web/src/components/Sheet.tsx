import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useId, useRef, type ReactNode } from "react";

const SPRING = { type: "spring", bounce: 0, duration: 0.45 } as const;

/**
 * 아래에서 올라오는 확인 시트. 되돌릴 수 없는 행동 앞에서 받는 사람·내용을 다시 보여 준다.
 * 손잡이를 아래로 밀거나, 바깥을 누르거나, Esc로 닫는다. 빠르게 밀면 조금만 밀어도 닫힌다.
 * PC에서는 화면 가운데 아래쪽에 폭 440px로 뜬다.
 * 시트가 열려 있는 동안 브라우저 뒤로가기(안드로이드 뒤로 버튼)는 화면을 나가지 않고 시트만 닫는다.
 */
export function Sheet({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: ReactNode }) {
  const reduce = useReducedMotion();
  const titleId = useId();
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    let pushed = false;
    let popped = false;
    const mark = `sheet-${Math.random()}`;
    const onPop = () => { popped = true; closeRef.current(); };
    /* 개발 모드의 이중 실행에서 기록이 어긋나지 않도록 한 박자 뒤에 쌓는다 */
    const t = window.setTimeout(() => {
      window.history.pushState({ ...(window.history.state ?? {}), sheet: mark }, "");
      window.addEventListener("popstate", onPop);
      pushed = true;
    }, 0);
    return () => {
      window.clearTimeout(t);
      if (!pushed) return;
      window.removeEventListener("popstate", onPop);
      if (!popped && window.history.state?.sheet === mark) window.history.back();
    };
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="fixed inset-0 z-50 flex items-end justify-center">
          <motion.div className="absolute inset-0 bg-scrim" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose} />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            className="relative grid w-full max-w-[440px] gap-3 rounded-t-[22px] bg-card px-5 pb-[max(24px,env(safe-area-inset-bottom))] pt-2 shadow-[0_-10px_30px_rgba(11,31,58,.18)] lg:mb-6 lg:rounded-[22px]"
            initial={reduce ? { opacity: 0 } : { y: "100%" }}
            animate={reduce ? { opacity: 1 } : { y: 0 }}
            exit={reduce ? { opacity: 0 } : { y: "100%", transition: { duration: 0.25, ease: [0.4, 0, 1, 1] } }}
            transition={SPRING}
            drag={reduce ? false : "y"}
            dragConstraints={{ top: 0, bottom: 0 }}
            dragElastic={{ top: 0.08, bottom: 1 }}
            onDragEnd={(_, i) => {
              if (i.offset.y > 90 || i.velocity.y > 500) onClose();
            }}
          >
            <div className="mx-auto mb-1 h-[5px] w-9 cursor-grab rounded-full bg-fill2" />
            <h2 id={titleId} className="text-head font-bold tracking-tight">
              {title}
            </h2>
            {children}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}
