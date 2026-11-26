import { useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { ApiError } from "@/api/client";
import { useAgreeConsents, useConsents } from "@/api/consents";
import { HOME, useSession } from "@/app/session";
import { PrimaryButton } from "@/components/Dock";
import { QueryState } from "@/components/QueryState";
import { useToast } from "@/components/Toast";
import { CONSENTS, type Consent } from "@/domain/consent";
import { ConsentChecklist, allAgreed } from "./ConsentChecklist";

/**
 * 로그인 뒤 필수 동의 (API 53~55 [제안]). 서버가 이 사람의 전 항목 동의를 확인하지 못하면(`consents_complete`가 false,
 * 또는 쓰기가 403 CONSENT_REQUIRED로 막힘) 이 화면으로 온다. 전 항목에 동의해야 저장되고, 저장 뒤 첫 화면으로 간다.
 */
export function ConsentAgreePage() {
  const { role, signOut, setConsentsComplete } = useSession();
  const nav = useNavigate();
  const from = (useLocation().state as { from?: string } | null)?.from;
  const toast = useToast();
  const busy = useRef(false); /* 같은 순간 두 번 눌려도 저장 요청은 한 번만 보낸다 */
  const q = useConsents();
  const agree = useAgreeConsents();
  const [on, setOn] = useState<string[]>([]);
  if (!role) return null;
  /* 서버가 이 사람에게 요구하는 항목 그대로 보여 주고 저장한다. 서버가 항목을 빼거나 더해도 화면이 맞는다 */
  const required = q.data?.items ?? [];
  const list: Consent[] = required.map((it) => CONSENTS.find((c) => c.id === it.item) ?? { id: it.item, title: it.label, who: [role], summary: "", refuse: "이용할 수 없어요" });

  const submit = () => {
    const version = q.data?.terms_version;
    if (!version || busy.current) return;
    busy.current = true;
    agree.mutate(
      { items: list.map((c) => c.id), terms_version: version },
      {
        onSettled: () => { busy.current = false; },
        onSuccess: () => {
          setConsentsComplete(true);
          toast({ kind: "ok", title: "동의를 저장했어요" });
          nav(from && from !== "/consents/agree" ? from : HOME[role], { replace: true });
        },
        onError: (e) => {
          if (e instanceof ApiError && e.code === "CONSENT_VERSION_MISMATCH") {
            q.refetch();
            setOn([]);
            toast({ kind: "error", title: "약관이 바뀌었어요", sub: "다시 읽고 동의해 주세요" });
          } else if (e instanceof ApiError && e.code === "CONSENT_INCOMPLETE") {
            toast({ kind: "error", title: "동의하지 않은 항목이 있어요", sub: "모든 항목에 동의해 주세요" });
          } else {
            toast({ kind: "error", title: "동의를 저장하지 못했어요", sub: "연결을 확인하고 다시 눌러 주세요" });
          }
        },
      },
    );
  };

  return (
    <div className="mx-auto min-h-dvh max-w-[480px] bg-g px-4 pb-40">
      <div className="flex min-h-11 items-center justify-end pt-2">
        <button type="button" onClick={() => { signOut(); nav("/login", { replace: true }); }} className="h-11 px-2 text-body font-medium text-accent">로그아웃</button>
      </div>
      <h1 className="text-large-title font-bold tracking-[-0.025em]">필수 동의</h1>
      <p className="mt-0.5 text-footnote font-medium text-ink2">서비스를 쓰려면 아래 항목에 모두 동의해 주세요</p>
      <QueryState queries={[q]} skeleton={3} errorTitle="동의 항목을 불러오지 못했어요">
        <ConsentChecklist role={role} on={on} setOn={setOn} afterLogin items={list} />
        <div className="glass fixed inset-x-0 bottom-0 z-20 mx-auto max-w-[480px] border-t border-sep bg-bar px-4 pb-[max(12px,env(safe-area-inset-bottom))] pt-2.5 backdrop-blur-xl">
          <PrimaryButton disabled={!allAgreed(list, on)} loading={agree.isPending} onClick={submit}>동의하고 시작하기</PrimaryButton>
        </div>
      </QueryState>
    </div>
  );
}
