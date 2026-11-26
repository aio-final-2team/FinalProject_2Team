import { useNavigate, useRouteError } from "react-router";
import { HOME, useSession } from "@/app/session";
import { StateView } from "./StateView";

/** 화면 코드가 예기치 않게 멈췄을 때 개발자용 오류 대신 보여 주는 화면. 다시 열기와 첫 화면으로만 둔다 */
export function RouteError() {
  const error = useRouteError();
  const nav = useNavigate();
  const { role } = useSession();
  if (import.meta.env.DEV) console.error(error);
  return (
    <div className="mx-auto grid min-h-dvh max-w-[480px] place-items-center bg-g px-4">
      <div role="alert" data-state="crash">
        <StateView
          kind="error"
          variant="server"
          audience={role === "parent" ? "parent" : "staff"}
          title="화면을 열지 못했어요"
          sub={"잠시 뒤 다시 열어 주세요.\n계속되면 선생님이나 관리자에게 알려 주세요"}
          action={{ label: "다시 열기", run: () => window.location.reload(), primary: true }}
        />
        <button type="button" onClick={() => nav(role ? HOME[role] : "/login", { replace: true })} className="mx-auto mt-1 block h-11 px-4 text-callout font-semibold text-accent">첫 화면으로</button>
      </div>
    </div>
  );
}
