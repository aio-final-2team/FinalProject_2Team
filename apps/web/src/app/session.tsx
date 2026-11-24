import { createContext, useContext, useState, type ReactNode } from "react";
import { api, setToken } from "@/api/client";
import type { Role } from "@/domain/types";

/** 로그인한 사람 (API 3.8 POST /auth/login, GET /me) */
export type SessionUser = { id: string; role: Role; display_name: string; org_id: string; classroom_ids: string[] };
type LoginRes = { access_token: string; token_type: string; user: SessionUser; children: { id: string; display_name: string; classroom_id: string }[] };

type Session = {
  role: Role | null;
  user: SessionUser | null;
  signIn: (loginId: string, password: string) => Promise<SessionUser>;
  signOut: () => void;
};
const Ctx = createContext<Session>({ role: null, user: null, signIn: async () => Promise.reject(), signOut: () => {} });
const KEY = "yuchion.user";

function read(): SessionUser | null {
  try {
    const v = sessionStorage.getItem(KEY);
    return v ? (JSON.parse(v) as SessionUser) : null;
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(read);
  const signIn = async (login_id: string, password: string) => {
    const r = await api<LoginRes>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ login_id, password }) });
    setToken(r.access_token);
    try {
      sessionStorage.setItem(KEY, JSON.stringify(r.user));
    } catch {
      /* 저장이 막혀도 이번 화면에서는 동작한다 */
    }
    setUser(r.user);
    return r.user;
  };
  const signOut = () => {
    setToken(null);
    try {
      sessionStorage.removeItem(KEY);
    } catch {
      /* 무시 */
    }
    setUser(null);
  };
  return <Ctx.Provider value={{ role: user?.role ?? null, user, signIn, signOut }}>{children}</Ctx.Provider>;
}

export const useSession = () => useContext(Ctx);
export const HOME: Record<Role, string> = { parent: "/parent/home", teacher: "/teacher/home", director: "/director/overview" };
/** 모의 API 데모 계정 (contracts/mock_api/README.md). 비밀번호는 모의 API 전용 값 */
export const DEMO_ACCOUNTS: Record<Role, string> = { parent: "parent01", teacher: "teacher01", director: "director01" };
export const DEMO_PASSWORD = "demo1234";
