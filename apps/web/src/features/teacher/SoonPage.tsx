import { BackLink } from "@/components/BackLink";
import { Navigate, useParams } from "react-router";
import { StateView } from "@/components/StateView";

/** 서버 API가 아직 없는 선생님 기능. 화면 틀만 두고 '준비 중'으로 구분한다 (API 문서 v0.8의 '제안' 항목). */
export const SOON = {
  photos: { title: "사진 정리", icon: "ai", sub: "알림장에 붙일 사진을 AI가 정리해요", note: "사진 AI는 첫 시연에서 가상 자료로 소개해요. 서버 API가 연결되면 열려요." },
  feed: { title: "우리 반 피드", icon: "document", sub: "반 소식을 학부모에게 올려요", note: "피드·앨범 API가 제안 단계예요. 연결되면 열려요." },
  album: { title: "앨범", icon: "document", sub: "반 앨범을 모아 봐요", note: "피드·앨범 API가 제안 단계예요. 연결되면 열려요." },
} as const;
export type SoonKey = keyof typeof SOON;

export function SoonPage() {
  const { key } = useParams();
  if (!key || !(key in SOON)) return <Navigate to="/teacher/home" replace />;
  const s = SOON[key as SoonKey];
  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10 pt-2">
      <BackLink to="/teacher/home" label="홈" />
      <h1 className="mt-1 text-large-title font-bold tracking-[-0.025em]">{s.title}</h1>
      <p className="mt-0.5 text-footnote font-medium text-ink2">{s.sub}</p>
      <div className="mt-6 grid place-items-center">
        <StateView kind="empty" audience="staff" title="준비 중이에요" sub={s.note} />
      </div>
    </div>
  );
}
