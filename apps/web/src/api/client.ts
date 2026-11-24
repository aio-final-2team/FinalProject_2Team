const BASE = import.meta.env.VITE_API_BASE_URL ?? "";
const TOKEN_KEY = "yuchion.token";

/** crypto.randomUUID는 https·localhost에서만 있다. 같은 와이파이 주소(http://192.168...)로 열어도 되게 대신할 값을 만든다 */
export function uuid(): string {
  if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
  const b = crypto.getRandomValues(new Uint8Array(16));
  b[6] = (b[6] & 0x0f) | 0x40;
  b[8] = (b[8] & 0x3f) | 0x80;
  const h = Array.from(b, (x) => x.toString(16).padStart(2, "0")).join("");
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-${h.slice(12, 16)}-${h.slice(16, 20)}-${h.slice(20)}`;
}

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
    /* 20초 안에 응답이 없으면 끊어서 화면이 '시간 초과' 상태를 보여 줄 수 있게 한다 (DOMException TimeoutError). 파일 올리기는 60초 */
    signal: init?.signal ?? AbortSignal.timeout(init?.body instanceof FormData ? 60_000 : 20_000),
    headers: {
      /* 파일 올리기(FormData)는 브라우저가 경계 문자열이 든 Content-Type을 직접 붙인다 */
      ...(init?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      "X-Request-ID": uuid(),
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
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

/** 사진 파일은 로그인 토큰이 있어야 받을 수 있어 <img src>에 주소만 넣으면 안 보인다. 토큰을 붙여 받은 뒤 임시 주소로 바꾼다 */
export async function fetchBlobUrl(path: string): Promise<string> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {}, signal: AbortSignal.timeout(30_000) });
  if (!res.ok) throw new ApiError(res.status, "사진을 불러오지 못했어요.");
  return URL.createObjectURL(await res.blob());
}
