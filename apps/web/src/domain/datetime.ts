/** 화면에 보이는 날짜 표기. 날짜는 "11월 25일", 날짜와 시간은 "11월 25일 00:11" 한 가지로 쓴다 */
const pad = (n: number) => String(n).padStart(2, "0");

export const fmtDate = (iso: string) => {
  const d = new Date(iso);
  return `${d.getMonth() + 1}월 ${d.getDate()}일`;
};

export const fmtDateTime = (iso: string) => {
  const d = new Date(iso);
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${pad(d.getHours())}:${pad(d.getMinutes())}`;
};
