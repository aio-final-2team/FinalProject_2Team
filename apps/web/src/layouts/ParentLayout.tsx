import { Outlet } from "react-router";
import { useState } from "react";
import { MeSheet } from "@/components/MeSheet";
import { TabBar } from "@/components/TabBar";

/** 학부모 화면 틀. 모바일 웹이 기준이고, PC에서는 가운데 앱 폭(480px)으로 보인다. 탭: 홈, 사진, (가운데 + 새 요청), 요청, 내 정보 */
export function ParentLayout() {
  const [me, setMe] = useState(false);
  const items = [
    { to: "/parent/home", icon: "home", label: "홈", also: ["/parent/notifications"] },
    { to: "/parent/feed", icon: "class", label: "사진" },
    { to: "/parent/requests", icon: "inquiry", label: "요청", not: ["/parent/requests/new"] },
  ];
  return (
    <div className="mx-auto min-h-full max-w-[480px] bg-g pb-[calc(76px+env(safe-area-inset-bottom))] lg:my-6 lg:min-h-[calc(100dvh-48px)] lg:rounded-[28px] lg:shadow-[0_20px_60px_-30px_rgba(11,31,58,.35)]">
      <Outlet />
      <TabBar className="max-w-[480px]" items={items} center={{ to: "/parent/requests/new", label: "새 요청 쓰기" }} extra={{ icon: "profile", label: "내 정보", onClick: () => setMe(true) }} />
      <MeSheet open={me} onClose={() => setMe(false)} />
    </div>
  );
}
