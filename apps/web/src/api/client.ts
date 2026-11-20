const BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const TOKEN_KEY = "yuchion.token";

/** 서버 오류 형식: { error: { code, message, details } } (API 설계 문서 1.4) */
export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public code?: string,
    public details?: unknown,
  ) {
    super(message);
  }
}

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(t: string | null) {
  try {
    if (t) sessionStorage.setItem(TOKEN_KEY, t);
    else sessionStorage.removeItem(TOKEN_KEY);
  } catch {
    /* 저장이 막힌 브라우저에서도 이번 화면에서는 동작한다 */
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Request-ID": crypto.randomUUID(),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let code: string | undefined;
    let message = "요청을 처리하지 못했어요.";
    let details: unknown;
    try {
      const body = await res.json();
      code = body?.error?.code;
      message = body?.error?.message ?? message;
      details = body?.error?.details;
    } catch {
      /* 본문이 JSON이 아닐 때 */
    }
    throw new ApiError(res.status, message, code, details);
  }
  return (await res.json()) as T;
}
