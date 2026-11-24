import { ScreenTop } from "@/components/ScreenTop";
import { useSession } from "@/app/session";
import { dateLabel, todayKST } from "@/domain/notes";
import { CareSection } from "./CareSection";

/** 귀가·투약 요청 (API 35·36, 문서 3.27 제안). 확인 → 완료 두 단계로 처리한다. */
export function CarePage({ role = "teacher" }: { role?: "teacher" | "director" }) {
  const { user } = useSession();
  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10 pt-2">
      <ScreenTop back={role === "teacher" ? { to: "/teacher/home", label: "홈" } : { to: "/director/overview", label: "현황" }} title="귀가·투약" sub={`${dateLabel(todayKST())} · 보호자가 보낸 요청을 확인해 주세요`} />
      <CareSection classroomId={user?.classroom_ids[0]} all={role === "director"} />
      <p className="mt-5 px-1 text-caption text-ink2">확인은 내용을 봤다는 기록이고, 완료는 실제로 먹이거나 인계한 뒤 눌러요. 완료 전에는 보호자 화면에서도 끝난 일로 보이지 않아요.</p>
    </div>
  );
}
