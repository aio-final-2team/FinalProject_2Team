import { useState, type ReactNode } from "react";
import { BackLink } from "./BackLink";
import { Buddy, SymbolMark } from "./Brand";
import { Icon } from "./Icon";
import { MeSheet } from "./MeSheet";

/**
 * 모든 화면의 맨 위 (제목 줄). 두 가지 모양만 쓴다.
 * - 탭 화면(back 없음): 브랜드 마크 줄(교사·원장 '온' 심볼, 학부모 말풍선 친구)과 오른쪽 버튼, 그 아래 큰 제목
 * - 들어간 화면(back 있음): 뒤로가기 하나와 큰 제목
 * 학부모 탭 화면은 오른쪽 끝에 내 정보 버튼이 자동으로 붙는다(교사·원장은 아래 탭에 있다).
 */
export function ScreenTop({ title, sub, back, right, audience = "staff" }: { title: ReactNode; sub?: ReactNode; back?: { to: string; label: string }; right?: ReactNode; audience?: "staff" | "parent" }) {
  const [me, setMe] = useState(false);
  return (
    <header>
      {back ? (
        <BackLink to={back.to} label={back.label} className="mt-2" />
      ) : (
        <div className="flex min-h-[52px] items-center justify-between pt-2">
          {audience === "parent" ? <Buddy face="basic" small className="size-8" /> : <SymbolMark className="size-8" />}
          <div className="flex items-center">
            {right}
            {audience === "parent" && (
              <button type="button" aria-label="내 정보" onClick={() => setMe(true)} className="grid size-11 place-items-center rounded-full text-ink active:scale-95">
                <Icon name="profile" className="size-6" />
              </button>
            )}
          </div>
        </div>
      )}
      <h1 className="mt-1 text-large-title font-bold tracking-[-0.025em]">{title}</h1>
      {sub && <p className="mt-0.5 text-footnote font-medium text-ink2">{sub}</p>}
      {audience === "parent" && !back && <MeSheet open={me} onClose={() => setMe(false)} />}
    </header>
  );
}
