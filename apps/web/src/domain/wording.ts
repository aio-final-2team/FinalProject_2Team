/**
 * 서버가 주는 문구를 화면 용어에 맞춘다. 화면은 "거절"로 통일했는데(교사·학부모 공통),
 * 서버의 상태 이름과 알림 제목에는 아직 "반려"가 남아 있다. 서버 문구를 바꾸기 전까지 웹에서 바꿔 보인다.
 */
export const term = <T extends string | null | undefined>(s: T): T => (typeof s === "string" ? (s.replace(/반려/g, "거절") as T) : s);
