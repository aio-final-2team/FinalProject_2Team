import { StateView } from "@/components/StateView";

/** 아직 만들지 않은 화면. 화면 목록은 Docs/Step2/유치온_T12_화면지도.md */
export function Later({ audience, title }: { audience: "parent" | "staff"; title: string }) {
  return (
    <div className="grid min-h-[60vh] place-items-center">
      <StateView kind="empty" audience={audience} title={title} sub="다음 단계에서 만들어요" />
    </div>
  );
}
