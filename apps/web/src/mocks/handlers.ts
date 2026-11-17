import { delay, http, HttpResponse } from "msw";
import type { Card, CardAction } from "@/domain/types";
import { seedCards } from "./data";

const base = import.meta.env.VITE_API_BASE_URL ?? "";
let cards = seedCards();
/** AC-05: 같은 키로 두 번 와도 한 번만 처리한다 */
const done = new Map<string, Card>();
const stamp = () => new Date().toISOString();

function apply(c: Card, a: CardAction, who: string): Card {
  const h = (what: string) => [...c.history, { at: stamp(), who, what }];
  switch (a.action) {
    case "approve_send":
      return { ...c, draft: a.draft ?? c.draft, status: "sent_or_booked", history: h("승인하고 보냄") };
    case "reject":
      return { ...c, status: "rejected", history: h(`반려 · ${a.reason}`) };
    case "hold":
      return { ...c, status: "on_hold", history: h(`보류 · ${a.until}까지 · ${a.reason}`) };
    case "escalate":
      return { ...c, escalated: true, status: "escalated", history: h("원장님께 올림") };
    case "complete":
      return { ...c, status: "completed", history: h(a.reason ? `처리 완료 · ${a.reason}` : "처리 완료") };
    case "reclassify":
      return { ...c, risk: a.risk, history: h(`다시 분류 → ${a.risk === "urgent" ? "긴급" : "일반"} · ${a.reason}`) };
    case "confirm_slot": {
      const s = c.slots?.find((x) => x.id === a.slotId);
      return { ...c, status: "sent_or_booked", history: h(`상담 확정 · ${s?.at ?? ""}`) };
    }
    case "note":
      return { ...c, directorNote: a.text, history: h("지시 남김") };
  }
}

export const handlers = [
  http.get(`${base}/api/cards`, async () => {
    await delay(450);
    return HttpResponse.json(cards);
  }),
  http.get(`${base}/api/cards/:id`, async ({ params }) => {
    await delay(250);
    const c = cards.find((x) => x.id === params.id);
    return c ? HttpResponse.json(c) : HttpResponse.json({ message: "not_found" }, { status: 404 });
  }),
  http.post(`${base}/api/cards/:id/actions`, async ({ params, request }) => {
    await delay(500);
    const key = request.headers.get("Idempotency-Key") ?? "";
    const prev = done.get(key);
    if (prev) return HttpResponse.json(prev, { headers: { "X-Idempotent-Replay": "true" } });
    const body = (await request.json()) as CardAction;
    const i = cards.findIndex((x) => x.id === params.id);
    if (i < 0) return HttpResponse.json({ message: "not_found" }, { status: 404 });
    const who = request.headers.get("X-Role") === "director" ? "원장" : "담임";
    cards[i] = apply(cards[i], body, who);
    done.set(key, cards[i]);
    return HttpResponse.json(cards[i]);
  }),
  http.post(`${base}/api/mock/reset`, () => {
    cards = seedCards();
    done.clear();
    return HttpResponse.json({ ok: true });
  }),
];
