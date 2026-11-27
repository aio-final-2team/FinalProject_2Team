/**
 * 서버가 주는 문구를 화면 용어에 맞춘다. 화면은 "거절"로 통일했는데(교사·학부모 공통),
 * 서버의 상태 이름과 알림 제목에는 아직 "반려"가 남아 있고, "카드"·"AI 판단 불확실" 같은 내부 말도 알림 제목에 나온다. 서버 문구를 바꾸기 전까지 웹에서 바꿔 보인다.
 */
export const term = <T extends string | null | undefined>(s: T): T =>
  typeof s === "string" ? (s.replace(/반려/g, "거절").replace(/새 카드가 왔어요/g, "새 요청이 왔어요").replace(/AI 판단 불확실 문의/g, "분류 확인이 필요한 문의") as T) : s;
