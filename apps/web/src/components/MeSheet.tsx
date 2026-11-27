import { useNavigate } from "react-router";
import { useSession } from "@/app/session";
import { SubButton } from "@/components/Dock";
import { Sheet } from "@/components/Sheet";

const ROLE_LABEL = { teacher: "담임 교사", director: "원장", parent: "보호자" } as const;

/** 내 정보: 이름·역할과 로그아웃. 교사·원장은 아래 탭, 학부모는 화면 머리의 내 정보 버튼에서 같은 시트를 연다 */
export function MeSheet({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { user, role, signOut } = useSession();
  const nav = useNavigate();
  return (
    <Sheet open={open} onClose={onClose} title="내 정보">
      <p className="text-callout"><b>{user?.display_name}</b> · {role ? ROLE_LABEL[role] : ""}</p>
      {role && <SubButton tone="tint" className="h-[52px] w-full" onClick={() => { onClose(); nav(`/${role}/memory`); }}>내 AI 기억</SubButton>}
      <SubButton tone="tint" className="h-[52px] w-full" onClick={() => { onClose(); nav("/consents"); }}>개인정보·동의 내역</SubButton>
      <SubButton tone="gray" className="h-[52px] w-full" onClick={() => { signOut(); nav("/login"); }}>로그아웃</SubButton>
    </Sheet>
  );
}
