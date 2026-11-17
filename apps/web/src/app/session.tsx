import { createContext, useContext, useState, type ReactNode } from "react";
import type { Role } from "@/domain/types";

/** 실제 로그인은 T10·T13 뒤에 붙인다. 지금은 시연 계정 역할만 기억한다. */
type Session = { role: Role | null; signIn: (r: Role) => void; signOut: () => void };
const Ctx = createContext<Session>({ role: null, signIn: () => {}, signOut: () => {} });
const KEY = "yuchion.role";

function read(): Role | null {
  try {
    const v = sessionStorage.getItem(KEY);
    return v === "parent" || v === "teacher" || v === "director" ? v : null;
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [role, setRole] = useState<Role | null>(read);
  const signIn = (r: Role) => {
    try {
      sessionStorage.setItem(KEY, r);
    } catch {
      /* 저장이 막힌 브라우저에서도 화면은 동작한다 */
    }
    setRole(r);
  };
  const signOut = () => {
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* 무시 */
    }
    setRole(null);
  };
  return <Ctx.Provider value={{ role, signIn, signOut }}>{children}</Ctx.Provider>;
}

export const useSession = () => useContext(Ctx);
export const HOME: Record<Role, string> = { parent: "/parent/home", teacher: "/teacher/inbox", director: "/director/inbox" };
