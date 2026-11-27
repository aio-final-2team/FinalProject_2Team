/** 알림장 타입 (API 설계 문서 v0.4 3.7·3.19~3.21·3.24) */

export type NoteStatus = "draft" | "needs_check" | "ready" | "sent";
export type ItemKey = "day" | "meal" | "medication" | "pickup" | "supplies" | "child";
export type SourceType = "teacher_input" | "document" | "request";
export type CheckKind =
  | "not_in_memo"
  | "sensitive"
  | "other_child"
  | "date_check"
  | "absent"
  | "draft_failed"
  | "check_failed"
  | "request_missed"
  | "return_limit";

export type NoteItem = {
  key: ItemKey;
  label: string;
  value: string;
  source: { type: SourceType; document_id?: string | null; document_title?: string | null; request_id?: string | null };
};

export type OpenCheck = {
  id: string;
  item_key: ItemKey;
  kind: CheckKind;
  problem: string;
  sentence: string | null;
  request_id?: string | null;
};

export type DailyNote = {
  id: string;
  child_id: string;
  note_date: string;
  status: NoteStatus;
  content: { items: NoteItem[] };
  open_checks: OpenCheck[];
  confirmed_at: string | null;
  sent_at: string | null;
  /** 서버가 항목마다 주는 초안 작업 ID와 입력 판, 보낸 뒤 정정한 시각 (문서 3.20·3.30) */
  input_id?: string;
  version?: number;
  corrected_at?: string | null;
  /** 보낸 알림장에 학부모가 남긴 답장(문의로 접수된 것)과 준비물 확인 시각 (문서 3.34, API 62·68) */
  replies?: NoteReply[];
  supplies_checked_at?: string | null;
};
export type NoteReply = { request_id: string; body: string; status: string; created_at: string };

export type Child = { id: string; display_name: string; classroom_id: string };
export type DraftStatus = "queued" | "running" | "succeeded" | "failed";
export type DraftJob = { input_id: string; draft_status: DraftStatus; error: { code: string; message: string } | null };

/** 교사 화면 표시 이름과 색 (디자인 시스템 1.4: 할 일=블루, 답 왔음·일반=라벤더, 완료=민트, 기다림=회색) */
export const NOTE_STATUS: Record<NoteStatus, { label: string; cls: string }> = {
  needs_check: { label: "확인 필요", cls: "text-accent" },
  draft: { label: "검사 통과", cls: "text-ink2" },
  ready: { label: "확인함", cls: "text-lav" },
  sent: { label: "보냈어요", cls: "text-ok" },
};

/** 확인 항목 종류별 제목과 선생님이 고를 수 있는 일 */
export const CHECK_KIND: Record<CheckKind, { title: string; short: string; fix?: string; keep?: string }> = {
  not_in_memo: { title: "메모에 없는 말이 들어갔어요", short: "메모에 없는 말", fix: "이 문장 빼기", keep: "실제로 있었던 일이에요" },
  sensitive: { title: "민감한 정보가 들어갔어요", short: "민감 정보", fix: "이 문장 빼기", keep: "보내도 되는 내용이에요" },
  other_child: { title: "다른 아이 이야기가 들어갔어요", short: "다른 아이 이름", fix: "이 문장 빼기", keep: "그대로 두기" },
  date_check: { title: "날짜를 확인해 주세요", short: "날짜 확인", keep: "확인했어요" },
  absent: { title: "결석한 아이예요", short: "결석", keep: "확인했어요" },
  draft_failed: { title: "이 아이 초안을 만들지 못했어요", short: "초안 실패", keep: "직접 쓰고 확인할게요" },
  check_failed: { title: "검사를 하지 못했어요", short: "검사 실패", keep: "직접 읽고 확인했어요" },
  request_missed: { title: "보호자 요청이 빠졌어요", short: "보호자 요청 누락", keep: "넣지 않기" },
  return_limit: { title: "AI가 고쳐도 남은 문제가 있어요", short: "남은 문제", keep: "직접 확인했어요" },
};

/** 서버는 투약 줄과 귀가 줄 이름을 둘 다 "보호자 요청"으로 준다. 무슨 요청인지 알 수 있게 종류로 바꾼다 */
export const itemLabel = (it: { key: string; label: string }) => (it.key === "medication" ? "투약" : it.key === "pickup" ? "귀가" : it.label);

export const SOURCE_LABEL: Record<SourceType, string> = {
  teacher_input: "선생님 입력",
  document: "원 자료",
  request: "보호자 요청",
};

/** 한국 날짜 YYYY-MM-DD. 초안은 오늘 또는 지난날만 만들 수 있다 */
export function todayKST(): string {
  const d = new Date(Date.now() + 9 * 3600_000);
  return d.toISOString().slice(0, 10);
}

/** 알림장 항목 글에 섞여 오는 마크다운 강조(**)를 화면에서는 걷어 낸다. 고치기 입력칸에는 원문을 그대로 둔다 */
export const noMd = (s: string) => s.replace(/\*\*/g, "");

export function dateLabel(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number);
  const w = ["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"][new Date(y, m - 1, d).getDay()];
  return `${m}월 ${d}일 ${w}`;
}

/** 이름 뒤 조사: 가온 → 가온이 */
export function nameI(n: string): string {
  const c = n.charCodeAt(n.length - 1);
  return c >= 0xac00 && c <= 0xd7a3 && (c - 0xac00) % 28 !== 0 ? `${n}이` : n;
}
