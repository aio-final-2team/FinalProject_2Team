import { useState } from "react";
import { useParams } from "react-router";
import { DOC_TYPE_LABEL, useDocument, type Chunk } from "@/api/documents";
import { Markdown } from "@/components/Markdown";
import { QueryState } from "@/components/QueryState";
import { ScreenTop } from "@/components/ScreenTop";

/** 통신문·식단표 본문 (API 29의 chunks). 의심 조각(suspicious)은 접어 두고 이유를 알려 준다 */
export function DocumentPage() {
  const { id } = useParams();
  const q = useDocument(id);
  const d = q.data;
  return (
    <div className="mx-auto max-w-[680px] px-4 pb-10">
      <ScreenTop back={{ to: "/teacher/class", label: "식단표와 가정통신문" }} title={d?.title ?? "자료"} sub={d ? `${DOC_TYPE_LABEL[d.doc_type] ?? "자료"} · ${d.effective_from}부터${d.effective_to ? ` ${d.effective_to}까지` : ""}` : undefined} />
      <QueryState queries={[q]} skeleton={3} errorTitle="자료를 불러오지 못했어요">
        {d && (
          <div className="mt-4 grid grid-cols-[minmax(0,1fr)] gap-3">
            {d.chunks && d.chunks.length > 0 ? (
              d.chunks.map((c) => <ChunkCard key={c.index} c={c} />)
            ) : (
              <p className="rounded-lg bg-card p-4 text-center text-callout text-ink2 shadow-card">본문이 아직 없어요</p>
            )}
          </div>
        )}
      </QueryState>
    </div>
  );
}

function ChunkCard({ c }: { c: Chunk }) {
  const [open, setOpen] = useState(!c.suspicious);
  /* 조각 본문이 '## 제목'으로 시작하면 위치 이름과 같아서 위치 줄은 생략한다 */
  /* 문서 안 위치가 본문이거나 "1쪽"처럼 쪽 번호뿐이면 알려 줄 게 없어서 숨긴다 */
  const showLoc = c.location && c.location !== "본문" && !/^\d+\s*쪽$/.test(c.location) && !c.content.trimStart().startsWith("#");
  return (
    <section className={`rounded-lg bg-card p-3 shadow-card ${c.suspicious ? "border-[1.5px] border-danger" : ""}`}>
      {c.suspicious && (
        <div className="mb-2">
          <b className="text-footnote text-danger">확인이 필요한 부분이에요</b>
          <p className="text-caption text-ink2">AI 보안 검사에서 걸러져서 검색과 답변에는 쓰지 않아요.</p>
          <button type="button" aria-expanded={open} onClick={() => setOpen((v) => !v)} className="mt-1 h-8 rounded-md bg-fill px-2.5 text-footnote font-semibold">{open ? "내용 접기" : "내용 보기"}</button>
        </div>
      )}
      {open && (
        <>
          {showLoc && <p className="mb-1 text-caption font-semibold text-ink2">{c.location}</p>}
          <Markdown text={c.content} />
        </>
      )}
    </section>
  );
}
