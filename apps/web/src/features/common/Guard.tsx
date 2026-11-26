import { Navigate, useLocation, useNavigate } from "react-router";
import type { ReactNode } from "react";
import type { Role } from "@/domain/types";
import { HOME, useSession } from "@/app/session";
import { StateView } from "@/components/StateView";

/** 화면에서 한 번 더 막지만, 실제 권한 검사는 서버가 한다 (T04 7.1, AC-06) */
export function Guard({ allow, children, skipConsent = false }: { allow: Role[]; children: ReactNode; skipConsent?: boolean }) {
  const { role, user } = useSession();
  const nav = useNavigate();
  const loc = useLocation();
  if (!role) return <Navigate to="/login" replace />;
  if (!allow.includes(role))
    return (
      <div className="grid min-h-full place-items-center">
        <StateView kind="forbidden" audience={role === "parent" ? "parent" : "staff"} title="이 화면은 볼 수 없어요" sub="내 역할의 화면만 볼 수 있어요" action={{ label: "내 첫 화면으로", run: () => nav(HOME[role]) }} />
      </div>
    );
  /* 필수 동의를 마치지 않았으면 먼저 동의 화면으로 보낸다 (API 53~55) */
  if (!skipConsent && user?.consents_complete === false) return <Navigate to="/consents/agree" replace state={{ from: `${loc.pathname}${loc.search}` }} />;
  return <>{children}</>;
}
