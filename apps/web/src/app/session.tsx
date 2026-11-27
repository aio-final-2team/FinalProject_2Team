import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, setToken } from "@/api/client";
import type { Role } from "@/domain/types";

/** 로그인한 사람 (API 3.8 POST /auth/login, GET /me) */
export type SessionUser = { id: string; role: Role; display_name: string; org_id: string; classroom_ids: string[]; consents_complete?: boolean };
type LoginRes = { access_token: string; token_type: string; user: SessionUser; children: { id: string; display_name: string; classroom_id: string }[] };

type Session = {
  role: Role | null;
  user: SessionUser | null;
  signIn: (loginId: string, password: string) => Promise<SessionUser>;
  signOut: () => void;
  /** 필수 동의를 마쳤는지 바꾼다 (동의 저장 후 true, 서버가 CONSENT_REQUIRED로 막으면 false) */
  setConsentsComplete: (done: boolean) => void;
};
const Ctx = createContext<Session>({ role: null, user: null, signIn: async () => Promise.reject(), signOut: () => {}, setConsentsComplete: () => {} });
const KEY = "yuchion.user";
/** 로고 모션을 이미 봤는지(이번 방문). 로그아웃하면 지워서 로그인 화면이 모션부터 다시 시작한다 */
export const SPLASH_KEY = "yuchion.splash";

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
  /* 계정이 바뀌면 화면 캐시(목록·사진)를 비운다. 같은 탭에서 다른 원으로 들어가도 앞 원 데이터가 보이지 않게 */
  const qc = useQueryClient();
  const signIn = async (login_id: string, password: string) => {
    const r = await api<LoginRes>("/api/v1/auth/login", { method: "POST", body: JSON.stringify({ login_id, password }) });
    qc.clear();
    setToken(r.access_token);
    try {
      sessionStorage.setItem(KEY, JSON.stringify(r.user));
    } catch {
      /* 저장이 막혀도 이번 화면에서는 동작한다 */
    }
    setUser(r.user);
    return r.user;
  };
  const setConsentsComplete = (done: boolean) =>
    setUser((u) => {
      if (!u) return u;
      const next = { ...u, consents_complete: done };
      try {
        sessionStorage.setItem(KEY, JSON.stringify(next));
      } catch {
        /* 무시 */
      }
      return next;
    });
  /* 서버가 필수 동의 없이 쓰기를 막으면(403 CONSENT_REQUIRED) 동의 화면으로 보낸다 */
  useEffect(() => {
    const h = () => setConsentsComplete(false);
    window.addEventListener("yuchion:consent-required", h);
    return () => window.removeEventListener("yuchion:consent-required", h);
  }, []);
  const signOut = () => {
    qc.clear();
    setToken(null);
    try {
      sessionStorage.removeItem(KEY);
      sessionStorage.removeItem(SPLASH_KEY);
    } catch {
      /* 무시 */
    }
    setUser(null);
  };
  return <Ctx.Provider value={{ role: user?.role ?? null, user, signIn, signOut, setConsentsComplete }}>{children}</Ctx.Provider>;
}

export const useSession = () => useContext(Ctx);
export const HOME: Record<Role, string> = { parent: "/parent/home", teacher: "/teacher/home", director: "/director/overview" };
/** 모의 API 데모 계정 (contracts/mock_api/README.md). 비밀번호는 모의 API 전용 값 */
export const DEMO_ACCOUNTS: Record<Role, string> = { parent: "parent01", teacher: "teacher01", director: "director01" };
export const DEMO_PASSWORD = "demo1234";
