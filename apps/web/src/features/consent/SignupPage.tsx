import { useState } from "react";
import { useNavigate } from "react-router";
import { BackLink } from "@/components/BackLink";
import { PrimaryButton } from "@/components/Dock";
import { Icon } from "@/components/Icon";
import { useToast } from "@/components/Toast";
import { saveConsent } from "@/domain/consent";
import { ConsentChecklist, allAgreed } from "./ConsentChecklist";
import type { Role } from "@/domain/types";

const ROLES: { role: Role; title: string; can: string[] }[] = [
  { role: "parent", title: "보호자", can: ["오늘 알림장과 우리 아이 사진 보기", "문의, 상담, 민원, 투약, 귀가 요청 보내기", "상담 가능한 시간 고르기"] },
  { role: "teacher", title: "교사", can: ["알림장 초안을 확인하고 보호자에게 보내기", "보호자 요청에 답하고 상담 확정하기", "귀가·투약 요청 확인하기"] },
  { role: "director", title: "원장", can: ["원 전체 현황 보기", "원장 보고 요청에 지시하기", "원 소식 관리와 통신문·식단표 올리기"] },
];

/**
 * 가입 동의 (팀 조사 문서 11/24). 역할을 고르면 그 역할이 받는 동의 항목이 나오고, 전부 동의해야 가입할 수 있다.
 * 얼굴 특징정보·건강 정보·AI 처리는 다른 동의와 따로 받아야 해서 항목마다 칸을 나눈다.
 */
export function SignupPage() {
  const nav = useNavigate();
  const toast = useToast();
  const [role, setRole] = useState<Role | null>(null);
  const [on, setOn] = useState<string[]>([]);
  return (
    <div className="mx-auto min-h-dvh max-w-[480px] bg-g px-4 pb-40">
      <BackLink to={role ? "/signup" : "/login"} label={role ? "역할 다시 고르기" : "로그인"} className="mt-2" onClick={role ? (e) => { e.preventDefault(); setRole(null); setOn([]); } : undefined} />
      <h1 className="mt-1 text-large-title font-bold tracking-[-0.025em]">가입</h1>
      {!role ? (
        <>
          <p className="mt-0.5 text-footnote font-medium text-ink2">어떤 역할로 가입하나요?</p>
          <ul aria-label="역할" className="mt-4 grid gap-2">
            {ROLES.map((r) => (
              <li key={r.role}>
                <button type="button" onClick={() => setRole(r.role)} className="w-full rounded-lg bg-card p-3 text-left shadow-card active:scale-[.99]">
                  <span className="flex items-center justify-between">
                    <b className="text-headline">{r.title}</b>
                    <Icon name="chevR" className="size-4 text-ink2" />
                  </span>
                  <span className="mt-1.5 block text-caption font-semibold text-ink2">이런 일을 할 수 있어요</span>
                  <ul className="mt-1 grid gap-1 text-footnote">
                    {r.can.map((c) => (
                      <li key={c} className="flex items-start gap-2"><span aria-hidden className="mt-[7px] size-1 shrink-0 rounded-full bg-accent" /><span className="break-keep">{c}</span></li>
                    ))}
                  </ul>
                </button>
              </li>
            ))}
          </ul>
        </>
      ) : (
        <>
          <p className="mt-0.5 text-footnote font-medium text-ink2">아래 항목에 모두 동의해야 가입할 수 있어요</p>
          <ConsentChecklist role={role} on={on} setOn={setOn} />
          <div className="glass fixed inset-x-0 bottom-0 z-20 mx-auto max-w-[480px] border-t border-sep bg-bar px-4 pb-[max(12px,env(safe-area-inset-bottom))] pt-2.5 backdrop-blur-xl">
            <PrimaryButton disabled={!allAgreed(role, on)} onClick={() => { saveConsent(role, on); toast({ kind: "ok", title: "동의를 저장했어요", sub: "이제 로그인할 수 있어요" }); nav("/login", { replace: true }); }}>동의하고 가입하기</PrimaryButton>
          </div>
        </>
      )}
    </div>
  );
}
