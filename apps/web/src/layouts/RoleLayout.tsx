import { useSession } from "@/app/session";
import { ParentLayout } from "./ParentLayout";
import { StaffLayout } from "./StaffLayout";

/** 역할 구분 없이 열리는 화면(동의 내역)이 그 역할의 탭 바와 '+' 버튼을 똑같이 갖도록 감싼다 */
export function RoleLayout() {
  const { role } = useSession();
  return role === "parent" ? <ParentLayout /> : <StaffLayout role={role === "director" ? "director" : "teacher"} />;
}
