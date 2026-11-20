import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ApiError } from "@/api/client";
import { DEMO_ACCOUNTS, DEMO_PASSWORD, HOME, useSession } from "@/app/session";
import logoOnBlue from "@/assets/logo/yuchion-main-logo-transparent.svg";
import { mountLogoMotion } from "@/assets/brand/yuchion-logo-motion.js";
import { Buddy, SymbolMark } from "@/components/Brand";
import { PrimaryButton, SubButton } from "@/components/Dock";
import type { Role } from "@/domain/types";

const DEMO = import.meta.env.VITE_DEMO_ACCOUNTS !== "false";
const SPLASH_KEY = "yuchion.splash";
const BLUE = "bg-[linear-gradient(160deg,#3D63F2,#2440C8)]";

function seenSplash(): boolean {
  try {
    return sessionStorage.getItem(SPLASH_KEY) === "1";
  } catch {
    return false;
  }
}

/**
 * C-01 로그인 (T12 화면지도 2.1, 디자인 시스템 6.3).
 * - 앱을 처음 열면 로고 모션 B(약 3.4초)가 한 번 나온다. 누르면 건너뛴다. 움직임 줄이기면 바로 끝난다.
 * - 끝나면 로고가 위로 올라가고 아래에서 로그인 시트가 올라온다. PC는 왼쪽 반 브랜드, 오른쪽 반 로그인 카드.
 * - 로그인 직후에는 글자 없이 역할 마크만 잠깐: 교사·원장 '온' 심볼 깜빡임, 학부모 말풍선 친구 hello.
 */
export function LoginPage() {
  const reduce = useReducedMotion();
  const [phase, setPhase] = useState<"splash" | "login" | "enter">(seenSplash() ? "login" : "splash");
  const [enterRole, setEnterRole] = useState<Role | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const ctl = useRef<{ skip: () => void; destroy: () => void } | null>(null);

  useEffect(() => {
    if (phase !== "splash" || !svgRef.current) return;
    ctl.current = mountLogoMotion(svgRef.current, {
      onDone: () => {
        try {
          sessionStorage.setItem(SPLASH_KEY, "1");
        } catch {
          /* 다음에 또 보여도 괜찮다 */
        }
        setTimeout(() => setPhase("login"), reduce ? 0 : 350);
      },
    });
    return () => ctl.current?.destroy();
  }, [phase, reduce]);

  return (
    <div className={`relative min-h-full overflow-hidden ${BLUE} lg:grid lg:grid-cols-2 lg:bg-none`}>
      {/* 브랜드 칸: 휴대폰은 위쪽, PC는 왼쪽 반 */}
      <div className={`relative flex items-center justify-center ${BLUE} ${phase === "splash" ? "h-dvh" : "h-[34dvh] lg:h-dvh"} transition-[height] duration-[420ms] ease-[cubic-bezier(.2,.9,.25,1)]`}>
        {phase === "splash" ? (
          <button className="absolute inset-0 grid place-items-center" onClick={() => ctl.current?.skip()} aria-label="로고 건너뛰기">
            <svg ref={svgRef} viewBox="40 40 560 280" className="w-[min(78vw,420px)]" aria-label="유치온" role="img" />
          </button>
        ) : (
          <motion.img
            src={logoOnBlue}
            alt="유치온"
            className="w-[min(52vw,260px)] lg:w-[min(30vw,360px)]"
            initial={reduce ? false : { y: 40, scale: 1.25 }}
            animate={{ y: 0, scale: 1 }}
            transition={{ duration: 0.42, ease: [0.2, 0.9, 0.25, 1] }}
          />
        )}
      </div>

      {/* 로그인 시트: 휴대폰은 아래에서 올라오는 흰 시트, PC는 오른쪽 반 가운데 카드 */}
      <AnimatePresence>
        {phase !== "splash" && (
          <motion.div
            className="relative min-h-[66dvh] rounded-t-xl bg-page px-5 pb-[max(24px,env(safe-area-inset-bottom))] pt-6 lg:flex lg:min-h-dvh lg:items-center lg:justify-center lg:rounded-none lg:px-10"
            initial={reduce ? { opacity: 0 } : { y: "100%" }}
            animate={reduce ? { opacity: 1 } : { y: 0 }}
            transition={{ type: "spring", bounce: 0.18, duration: 0.55 }}
          >
            <LoginForm
              onEnter={(r) => {
                setEnterRole(r);
                setPhase("enter");
              }}
            />
          </motion.div>
        )}
      </AnimatePresence>

      {/* 로그인 직후 역할 마크 */}
      <AnimatePresence>{phase === "enter" && enterRole && <EnterMark role={enterRole} />}</AnimatePresence>
    </div>
  );
}

function EnterMark({ role }: { role: Role }) {
  const nav = useNavigate();
  const reduce = useReducedMotion();
  useEffect(() => {
    const t = setTimeout(() => nav(HOME[role]), reduce ? 150 : 900);
    return () => clearTimeout(t);
  }, [nav, role, reduce]);
  return (
    <motion.div className="fixed inset-0 z-50 grid place-items-center bg-page" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} aria-live="polite">
      <span className="sr-only">들어가는 중</span>
      {role === "parent" ? <Buddy face="hello" className="size-24" /> : <SymbolMark motion="blink" className="size-20" />}
    </motion.div>
  );
}

function LoginForm({ onEnter }: { onEnter: (r: Role) => void }) {
  const { signIn } = useSession();
  const [id, setId] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const login = async (loginId: string, password: string) => {
    setBusy(true);
    setErr("");
    try {
      const u = await signIn(loginId, password);
      onEnter(u.role);
    } catch (e) {
      /* 아이디·비밀번호 중 무엇이 틀렸는지는 알려 주지 않는다 */
      setErr(e instanceof ApiError && e.status === 401 ? "아이디나 비밀번호가 맞지 않아요." : "로그인 서버에 연결하지 못했어요. 모의 API(8000)를 켜 주세요.");
    } finally {
      setBusy(false);
    }
  };
  const field = "h-12 w-full rounded-md border-[1.5px] border-line bg-card px-3 text-body outline-none focus:border-accent focus:shadow-[0_0_0_3px_var(--tint)]";

  return (
    <div className="mx-auto grid w-full max-w-[400px] gap-5">
      <form
        className="grid gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          login(id.trim(), pw);
        }}
      >
        <h1 className="text-large-title font-bold tracking-[-0.025em]">로그인</h1>
        <label className="grid gap-1.5">
          <span className="text-footnote font-semibold">아이디</span>
          <input value={id} onChange={(e) => setId(e.target.value)} onFocus={() => DEMO && !id && setId(DEMO_ACCOUNTS.teacher)} autoComplete="username" className={field} />
        </label>
        <label className="grid gap-1.5">
          <span className="text-footnote font-semibold">비밀번호</span>
          <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} onFocus={() => DEMO && !pw && setPw(DEMO_PASSWORD)} autoComplete="current-password" className={field} />
        </label>
        {err && (
          <p role="alert" className="text-footnote font-medium text-danger">
            {err}
          </p>
        )}
        <PrimaryButton type="submit" loading={busy} className="mt-1">
          로그인
        </PrimaryButton>
      </form>
      {DEMO && (
        <div className="grid gap-2">
          <div className="flex items-center gap-3 text-footnote text-ink2">
            <span className="h-px flex-1 bg-sep" />
            시연 계정
            <span className="h-px flex-1 bg-sep" />
          </div>
          <div className="grid grid-cols-3 gap-2">
            {(["parent", "teacher", "director"] as Role[]).map((r) => (
              <SubButton key={r} onClick={() => login(DEMO_ACCOUNTS[r], DEMO_PASSWORD)} disabled={busy}>
                {r === "parent" ? "학부모로" : r === "teacher" ? "선생님으로" : "원장으로"}
              </SubButton>
            ))}
          </div>
          <p className="text-center text-caption text-ink2">직접 입력: teacher01 · parent01 · director01 / 비밀번호 demo1234 (모의 API)</p>
        </div>
      )}
    </div>
  );
}
