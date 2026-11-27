import { useEffect } from "react";
import { useQueryClient, type QueryKey } from "@tanstack/react-query";
import { getToken } from "./client";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "";

/**
 * AI 진행 스트림(API 6·14, SSE)을 읽는다. 토큰을 헤더로 보내야 해서 EventSource 대신 fetch 스트림을 쓴다.
 * 단계·카드·완료 이벤트가 올 때마다 화면 데이터를 다시 불러온다. 스트림이 안 열리거나 끊기면 조용히 멈추고,
 * 쿼리의 느린 새로고침이 그 자리를 이어받는다. 한 번 연결하고 다시 붙이지 않는다.
 */
export function useLiveStream(path: string | undefined, queryKey: QueryKey) {
  const qc = useQueryClient();
  const key = JSON.stringify(queryKey);
  useEffect(() => {
    if (!path) return;
    const ctl = new AbortController();
    const token = getToken();
    (async () => {
      try {
        const res = await fetch(`${BASE}${path}`, { headers: { Accept: "text/event-stream", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, signal: ctl.signal });
        if (!res.ok || !res.body) return;
        const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += value;
          const parts = buf.split("\n\n");
          buf = parts.pop() ?? "";
          for (const p of parts) if (p.includes("event:")) qc.invalidateQueries({ queryKey });
        }
        qc.invalidateQueries({ queryKey });
      } catch {
        /* 끊기면 쿼리의 새로고침이 이어받는다 */
      }
    })();
    return () => ctl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, key, qc]);
}
