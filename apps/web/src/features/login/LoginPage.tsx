import { useState } from "react";
import { useNavigate } from "react-router";
import logoLight from "@/assets/logo/yuchion-main-logo-light-transparent.svg";
import logoDark from "@/assets/logo/yuchion-main-logo-dark-transparent.svg";
import { HOME, useSession } from "@/app/session";
import { Button } from "@/components/Button";
import type { Role } from "@/domain/types";

const DEMO = import.meta.env.VITE_DEMO_ACCOUNTS !== "false";

/** C-01 로그인. 시연 계정 버튼은 배포 설정(VITE_DEMO_ACCOUNTS=false)으로 끈다. 로고 모션은 다음 단계. */
export function LoginPage() {
  const { signIn } = useSession();
  const nav = useNavigate();
  const [id, setId] = useState("");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const go = (r: Role) => {
    signIn(r);
    nav(HOME[r]);
  };
  return (
    <div className="grid min-h-full place-items-center px-5 py-10">
      <div className="grid w-full max-w-[400px] gap-6">
        <div className="text-center">
          <img src={logoLight} alt="유치온" className="mx-auto h-14 w-auto dark:hidden" />
          <img src={logoDark} alt="유치온" className="mx-auto hidden h-14 w-auto dark:block" />
        </div>
        <form
          className="grid gap-3 rounded-[22px] bg-card p-6"
          onSubmit={(e) => {
            e.preventDefault();
            /* 실제 로그인 API(T13)가 붙기 전에는 항상 실패한다. 어느 쪽이 틀렸는지는 알려 주지 않는다. */
            setErr("아이디나 비밀번호가 맞지 않아요.");
          }}
        >
          <h1 className="mb-1 text-head font-bold">로그인</h1>
          <label className="grid gap-1.5">
            <span className="text-sub font-semibold text-ink2">아이디</span>
            <input value={id} onChange={(e) => setId(e.target.value)} autoComplete="username" className="rounded-xl border-[1.5px] border-transparent bg-fill px-3.5 py-3 text-body outline-none transition focus:border-accent focus:shadow-[0_0_0_4px_var(--tint)]" />
          </label>
          <label className="grid gap-1.5">
            <span className="text-sub font-semibold text-ink2">비밀번호</span>
            <input type="password" value={pw} onChange={(e) => setPw(e.target.value)} autoComplete="current-password" className="rounded-xl border-[1.5px] border-transparent bg-fill px-3.5 py-3 text-body outline-none transition focus:border-accent focus:shadow-[0_0_0_4px_var(--tint)]" />
          </label>
          {err && <p role="alert" className="text-sub text-danger">{err}</p>}
          <Button type="submit" className="mt-1">로그인</Button>
        </form>
        {DEMO && (
          <div className="grid gap-2">
            <p className="text-center text-sub text-ink2">시연 계정으로 둘러보기</p>
            <div className="grid grid-cols-3 gap-2">
              <Button variant="tinted" size="sm" className="h-10" onClick={() => go("parent")}>학부모</Button>
              <Button variant="tinted" size="sm" className="h-10" onClick={() => go("teacher")}>선생님</Button>
              <Button variant="tinted" size="sm" className="h-10" onClick={() => go("director")}>원장</Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
