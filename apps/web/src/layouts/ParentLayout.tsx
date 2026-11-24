import { Outlet } from "react-router";
import { TabBar } from "@/components/TabBar";

/** 학부모 화면 틀. 모바일 웹이 기준이고, PC에서는 가운데 앱 폭(480px)으로 보인다. 탭: 홈, 소식, (가운데 + 새 요청), 요청, 우리 애 */
export function ParentLayout() {
  const items = [
    { to: "/parent/home", icon: "home", label: "홈" },
    { to: "/parent/feed", icon: "class", label: "소식" },
    { to: "/parent/requests", icon: "inquiry", label: "요청" },
    { to: "/parent/album", icon: "profile", label: "우리 애" },
  ];
  return (
    <div className="mx-auto min-h-full max-w-[480px] bg-g pb-[calc(76px+env(safe-area-inset-bottom))] lg:my-6 lg:min-h-[calc(100dvh-48px)] lg:rounded-[28px] lg:shadow-[0_20px_60px_-30px_rgba(11,31,58,.35)]">
      <Outlet />
      <TabBar className="max-w-[480px]" items={items} center={{ to: "/parent/requests/new", label: "새 요청 쓰기" }} />
    </div>
  );
}
