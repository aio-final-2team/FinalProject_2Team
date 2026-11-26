import type { ReactNode } from "react";

/** 굵게(**글**)만 처리한다. 자료 본문에는 HTML을 넣지 않고 글자로만 그린다 */
function inline(s: string): ReactNode[] {
  return s.split(/(\*\*[^*]+\*\*)/g).map((p, i) => (p.startsWith("**") && p.endsWith("**") ? <b key={i}>{p.slice(2, -2)}</b> : p));
}
const isRow = (l: string) => /^\s*\|.*\|\s*$/.test(l);
const cells = (l: string) => l.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());

/** 자료 본문용 간단한 마크다운: 제목(#), 목록(- / 1.), 표(| |), 문단. 식단표·일정표가 표로 와서 표를 꼭 그린다 */
export function Markdown({ text, className = "" }: { text: string; className?: string }) {
  const lines = text.split("\n");
  const out: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const l = lines[i];
    if (!l.trim()) { i++; continue; }
    const h = l.match(/^(#{1,4})\s+(.*)$/);
    if (h) { out.push(<h4 key={i} className="mt-3 text-callout font-bold first:mt-0">{inline(h[2])}</h4>); i++; continue; }
    if (isRow(l)) {
      const rows: string[][] = [];
      while (i < lines.length && isRow(lines[i])) { if (!/^\s*\|[\s:|-]+\|\s*$/.test(lines[i])) rows.push(cells(lines[i])); i++; }
      const [head, ...body] = rows;
      out.push(
        <div key={i} className="mt-2 overflow-x-auto rounded-md border border-sep">
          <table className="w-full min-w-max border-collapse text-footnote">
            <thead className="bg-fill"><tr>{head.map((c, k) => <th key={k} className="px-3 py-2 text-left font-semibold">{inline(c)}</th>)}</tr></thead>
            <tbody>{body.map((r, k) => <tr key={k} className="border-t border-sep">{r.map((c, j) => <td key={j} className="px-3 py-2 align-top">{inline(c)}</td>)}</tr>)}</tbody>
          </table>
        </div>,
      );
      continue;
    }
    if (/^\s*([-*]|\d+\.)\s+/.test(l)) {
      const ordered = /^\s*\d+\./.test(l);
      const items: string[] = [];
      while (i < lines.length && /^\s*([-*]|\d+\.)\s+/.test(lines[i])) { items.push(lines[i].replace(/^\s*([-*]|\d+\.)\s+/, "")); i++; }
      const Tag = ordered ? "ol" : "ul";
      out.push(<Tag key={i} className={`mt-1.5 grid gap-1 pl-5 text-callout ${ordered ? "list-decimal" : "list-disc"}`}>{items.map((t, k) => <li key={k} className="break-keep">{inline(t)}</li>)}</Tag>);
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !isRow(lines[i]) && !/^(#{1,4})\s+/.test(lines[i]) && !/^\s*([-*]|\d+\.)\s+/.test(lines[i])) { para.push(lines[i]); i++; }
    out.push(<p key={i} className="mt-1.5 whitespace-pre-line break-keep text-callout">{inline(para.join("\n"))}</p>);
  }
  return <div className={className}>{out}</div>;
}
