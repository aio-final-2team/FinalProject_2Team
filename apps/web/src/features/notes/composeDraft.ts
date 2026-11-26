/**
 * 알림장 입력(오늘 활동, 준비물)을 이 기기에 임시 저장한다. 화면을 옮기거나 새로고침해도 적던 내용이 남는다.
 * 서버에 임시 저장 API가 없어서 브라우저에만 둔다. 초안 만들기를 시작하면 지운다. 반·날짜마다 따로 둔다.
 */
export type ComposeDraft = { activities: string; supplies: string };
const key = (cid: string, date: string) => `yuchion.compose.${cid}.${date}`;

export function loadCompose(cid: string, date: string): ComposeDraft {
  try {
    const v = JSON.parse(localStorage.getItem(key(cid, date)) ?? "{}");
    return { activities: typeof v.activities === "string" ? v.activities : "", supplies: typeof v.supplies === "string" ? v.supplies : "" };
  } catch {
    return { activities: "", supplies: "" };
  }
}

export function saveCompose(cid: string, date: string, d: ComposeDraft) {
  try {
    if (!d.activities && !d.supplies) localStorage.removeItem(key(cid, date));
    else localStorage.setItem(key(cid, date), JSON.stringify(d));
  } catch {
    /* 저장이 막힌 브라우저면 이번 화면에서만 유지한다 */
  }
}

export const clearCompose = (cid: string, date: string) => saveCompose(cid, date, { activities: "", supplies: "" });
