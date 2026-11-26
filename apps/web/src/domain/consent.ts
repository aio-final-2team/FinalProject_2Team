import type { Role } from "./types";

/**
 * 가입 때 받는 동의 6개 (팀 조사 문서 11/24: 전부 필수). 문구는 조사 문서의 화면 문구 초안 그대로("~합니다")이고, AI 처리 항목에 영민님 제안 한 줄을 더했다.
 * 항목 id는 서버(API 53~55)의 항목 이름과 같다. 로그인한 사람의 동의는 서버가 저장한다.
 */
export type Consent = { id: string; title: string; who: Role[]; summary: string; separate?: boolean; refuse?: string };

const ALL: Role[] = ["parent", "teacher", "director"];
export const CONSENTS: Consent[] = [
  { id: "terms", title: "이용약관", who: ALL, summary: "서비스 이용약관에 동의합니다." },
  { id: "privacy", title: "개인정보 수집·이용", who: ALL, summary: "이름·연락처·역할 정보를 가입과 소통 기능에 씁니다. 탈퇴할 때까지 보관합니다." },
  { id: "ai_processing", title: "AI 처리", who: ALL, separate: true, summary: "내가 쓴 글이 AI 처리를 위해 OpenAI(미국)로 전송됩니다. AI 학습에는 쓰지 않습니다. 보호자·선생님이 쓴 글은 모델로 보내기 전에 전화번호·주민번호·계좌·이메일을 가립니다. AI가 처리한 기록(보낸 글·받은 답)은 오류 점검을 위해 LangSmith(미국)에 14일 보관한 뒤 지웁니다." },
  { id: "child_info", title: "자녀 개인정보 수집", who: ["parent"], summary: "자녀 이름·생년월일·반·사진·알림장을 받습니다.", refuse: "자녀를 등록할 수 없습니다" },
  { id: "child_health", title: "자녀 건강·투약 정보", who: ["parent"], separate: true, summary: "투약·알레르기 같은 건강 정보를 투약 요청 처리에 씁니다." },
  { id: "child_face", title: "자녀 얼굴로 찾기", who: ["parent"], separate: true, summary: "사진에서 우리 아이를 찾기 위해 얼굴 특징정보를 만들어 AWS(서울)에서 처리합니다. 탈퇴하면 지웁니다." },
];
export const consentsFor = (role: Role) => CONSENTS.filter((c) => c.who.includes(role));

const key = (role: Role) => `yuchion.consent.${role}`;
export type ConsentRecord = { ids: string[]; at: string };
export function saveConsent(role: Role, ids: string[]) {
  try { localStorage.setItem(key(role), JSON.stringify({ ids, at: new Date().toISOString() } satisfies ConsentRecord)); } catch { /* 저장이 막혀도 이번 화면에서는 계속 쓴다 */ }
}
export function loadConsent(role: Role): ConsentRecord | null {
  try { return JSON.parse(localStorage.getItem(key(role)) ?? "null"); } catch { return null; }
}
