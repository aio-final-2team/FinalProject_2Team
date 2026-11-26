import { useState } from "react";
import { HOME, useSession } from "@/app/session";
import { Button } from "@/components/Button";
import { ScreenTop } from "@/components/ScreenTop";
import { Sheet } from "@/components/Sheet";
import { useConsents } from "@/api/consents";
import { QueryState } from "@/components/QueryState";
import { CONSENTS } from "@/domain/consent";

/** 개인정보·동의 내역: 동의한 항목과 날짜, 동의를 거두는 방법(탈퇴). 원장은 외부 처리 업체도 본다 (팀 조사 문서 11/24) */
export function ConsentsPage() {
  const { role, user } = useSession();
  const [quit, setQuit] = useState(false);
  const q = useConsents();
  if (!role) return null;
  const day = (iso: string) => new Date(iso).toLocaleDateString("ko-KR", { year: "numeric", month: "long", day: "numeric" });
  return (
    <div className={`mx-auto min-h-dvh bg-g px-4 pb-10 ${role === "parent" ? "max-w-[480px]" : "max-w-[680px]"}`}>
      <ScreenTop audience={role === "parent" ? "parent" : "staff"} back={{ to: HOME[role], label: "돌아가기" }} title="개인정보·동의 내역" sub={user?.display_name} />
      <QueryState queries={[q]} skeleton={3} errorTitle="동의 내역을 불러오지 못했습니다">
        <ul className="mt-4 overflow-hidden rounded-lg bg-card shadow-card [&>li+li]:border-t [&>li+li]:border-sep">
          {(q.data?.items ?? []).map((it) => {
            const c = CONSENTS.find((x) => x.id === it.item);
            return (
              <li key={it.item} className="px-3 py-3">
                <div className="flex items-center justify-between gap-2">
                  <b className="text-callout">{c?.title ?? it.label}</b>
                  <span className={`shrink-0 rounded-full px-2 py-0.5 text-caption font-semibold ${it.agreed_at ? "bg-ok-tint text-ok" : "bg-fill text-ink2"}`}>{it.agreed_at ? "동의함" : "동의 전"}</span>
                </div>
                {c && <p className="mt-1 break-keep text-footnote text-ink2">{c.summary}</p>}
                {it.agreed_at && <p className="mt-0.5 text-caption text-ink2">{day(it.agreed_at)}에 동의했습니다</p>}
              </li>
            );
          })}
        </ul>
      </QueryState>
      {role === "director" && (
        <section className="mt-5 rounded-lg bg-card p-3 shadow-card" aria-label="외부 처리 업체">
          <b className="block text-callout">외부 처리 업체</b>
          <ul className="mt-1.5 grid gap-1 text-footnote text-ink2">
            <li>OpenAI(미국): 쓴 글의 AI 처리</li>
            <li>AWS(서울): 사진에서 아이 얼굴 찾기</li>
          </ul>
        </section>
      )}
      <p className="mt-4 break-keep px-1 text-footnote text-ink2">탈퇴하면 올린 글, 사진, 얼굴 특징정보를 지웁니다.</p>
      <button type="button" onClick={() => setQuit(true)} className="mt-3 h-11 w-full rounded-md bg-fill text-callout font-semibold text-ink active:scale-[.98]">탈퇴하기</button>
      <Sheet open={quit} onClose={() => setQuit(false)} title="탈퇴는 준비 중입니다">
        <p className="text-footnote text-ink2">탈퇴 기능이 열리면 이 화면에서 할 수 있습니다.</p>
        <Button variant="plain" size="sm" onClick={() => setQuit(false)}>닫기</Button>
      </Sheet>
    </div>
  );
}
