import type { ReactNode } from "react";
import { useNavigate } from "react-router";
import { HOME, useSession } from "@/app/session";
import type { UseQueryResult } from "@tanstack/react-query";
import { ApiError } from "@/api/client";
import { SkeletonRows, StateView, type Variant } from "./StateView";

/**
 * 화면 상태(불러오는 중·오류·최신 내용 못 받음)를 한 곳에서 정한다.
 * 오류 연출(움직임·애니메이션)을 나중에 고도화할 때는 이 파일의 ErrorState만 바꾸면 모든 화면에 적용된다.
 */

/**
 * 실패 원인을 6가지로 나눈다. 원인마다 상태 화면의 마크·배지가 다르다 (StateView의 Variant).
 * 서버 오류 · 연결 끊김 · 시간 초과 · 권한 없음(403) · 없는 내용(404) · 방금 바뀜(409)
 */
export function errorText(error: unknown): { variant: Variant; title: string; sub: string } {
  if (error instanceof ApiError) {
    if (error.status === 403) return { variant: "forbidden", title: "이 내용은 볼 수 없어요", sub: "내 반 또는 내 권한의 내용만 볼 수 있어요" };
    if (error.status === 404) return { variant: "notfound", title: "찾는 내용이 없어요", sub: "지워졌거나 다른 반의 내용일 수 있어요" };
    if (error.status === 409) return { variant: "conflict", title: "내용이 방금 바뀌었어요", sub: "최신 내용을 다시 불러와서 확인해 주세요" };
    if (error.status >= 500) return { variant: "server", title: "서버가 잠시 응답하지 않아요", sub: "잠시 뒤 다시 시도해 주세요. 쓰던 내용은 그대로예요" };
    return { variant: "server", title: "불러오지 못했어요", sub: error.message };
  }
  if (error instanceof DOMException && (error.name === "TimeoutError" || error.name === "AbortError")) return { variant: "timeout", title: "응답이 너무 늦어요", sub: "연결이 느린 것 같아요. 다시 시도해 주세요" };
  return { variant: "offline", title: "연결이 끊겼어요", sub: "네트워크를 확인하고 다시 시도해 주세요. 쓰던 내용은 그대로예요" };
}

export function ErrorState({ error, onRetry, updatedAt, title, retrying }: { error?: unknown; onRetry: () => void; updatedAt?: number; title?: string; retrying?: boolean }) {
  const t = errorText(error);
  const nav = useNavigate();
  const { role } = useSession();
  const retryable = t.variant === "server" || t.variant === "offline" || t.variant === "timeout" || t.variant === "conflict";
  const when = retryable && updatedAt ? `\n마지막으로 불러온 시각 ${new Date(updatedAt).toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit" })}` : "";
  /* 할 수 있는 일 하나만 (7.15): 오류는 다시 시도, 권한 없음·없는 내용은 내 첫 화면으로 */
  const action = retryable ? { label: retrying ? "다시 불러오는 중…" : t.variant === "conflict" ? "최신 내용 보기" : "다시 시도", run: onRetry } : { label: "내 첫 화면으로", run: () => nav(role ? HOME[role] : "/login") };
  return (
    <div data-state="error" data-variant={t.variant}>
      <StateView kind={t.variant === "forbidden" ? "forbidden" : t.variant === "notfound" ? "empty" : "error"} variant={t.variant} audience={role === "parent" ? "parent" : "staff"} title={retryable && t.variant !== "conflict" ? (title ?? t.title) : t.title} sub={`${t.sub}${when}`} action={action} />
    </div>
  );
}

/** 이미 받은 내용은 보여 주면서 새로 받지 못했다는 것만 알리는 띠 */
export function StaleBanner({ queries }: { queries: UseQueryResult<unknown>[] }) {
  const failed = queries.find((q) => q.isError && q.data !== undefined);
  if (!failed) return null;
  return (
    <div role="status" data-state="stale" className="mb-3 flex items-center justify-between gap-2 rounded-lg bg-card px-3 py-2.5 text-footnote shadow-card">
      <span className="min-w-0 whitespace-pre-line break-keep text-pretty">{"최신 내용을 불러오지 못했어요.\n보이는 내용은 마지막으로 받은 내용이에요"}</span>
      <button type="button" onClick={() => queries.forEach((q) => q.isError && q.refetch())} className="h-8 shrink-0 rounded-md bg-tint px-2.5 font-semibold text-accent-ink active:scale-[.97]">
        다시 시도
      </button>
    </div>
  );
}

/**
 * queries를 모두 기다린다. 하나라도 처음부터 못 받으면 오류 화면, 받은 적이 있으면 children과 함께 StaleBanner를 보여 준다.
 */
export function QueryState({ queries, children, skeleton = 4, errorTitle }: { queries: UseQueryResult<unknown>[]; children: ReactNode; skeleton?: number; errorTitle?: string }) {
  const hard = queries.find((q) => q.isError && q.data === undefined);
  if (hard) {
    return <ErrorState error={hard.error} title={errorTitle} updatedAt={hard.dataUpdatedAt || undefined} retrying={queries.some((q) => q.isFetching)} onRetry={() => queries.forEach((q) => q.isError && q.refetch())} />;
  }
  if (queries.some((q) => q.isLoading)) return <div data-state="loading" aria-busy="true"><SkeletonRows n={skeleton} /></div>;
  return (
    <>
      <StaleBanner queries={queries} />
      {children}
    </>
  );
}
