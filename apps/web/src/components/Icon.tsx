const raw = import.meta.glob("../assets/icons/*.svg", { query: "?raw", import: "default", eager: true }) as Record<string, string>;

const ICONS: Record<string, string> = {};
for (const [path, svg] of Object.entries(raw)) {
  const name = path.split("/").pop()!.replace(".svg", "");
  ICONS[name] = svg.replace(/\s(width|height)="24"/g, "").replace("<svg ", '<svg width="100%" height="100%" ');
}
/* 에셋 폴더에 없는 아이콘은 같은 선 굵기로 직접 그린다 */
const S = 'xmlns="http://www.w3.org/2000/svg" width="100%" height="100%" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"';
Object.assign(ICONS, {
  bell: `<svg ${S}><path d="M6 16V11a6 6 0 1 1 12 0v5l1.5 2h-15z"/><path d="M10 21h4"/></svg>`,
  chevL: `<svg ${S} stroke-width="2.4"><path d="M15 5l-7 7 7 7"/></svg>`,
  chevR: `<svg ${S} stroke-width="2.2"><path d="M9 6l6 6-6 6"/></svg>`,
  plus: `<svg ${S} stroke-width="2.2"><path d="M12 5v14M5 12h14"/></svg>`,
  check: `<svg ${S} stroke-width="3"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>`,
  lock: `<svg ${S}><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>`,
  logout: `<svg ${S}><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3"/><path d="M10 17l-5-5 5-5M5 12h11"/></svg>`,
  photo: `<svg ${S}><rect x="3" y="5" width="18" height="15" rx="3"/><circle cx="9" cy="10" r="2"/><path d="M4 17l4.5-4 3.5 3 2.5-2 5.5 5"/></svg>`,
  write: `<svg ${S}><path d="M12 20H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h7"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L11 15l-4 1 1-4z"/></svg>`,
});

export type IconName = keyof typeof ICONS | string;

export function Icon({ name, className = "size-[1em]" }: { name: IconName; className?: string }) {
  return <span aria-hidden className={`inline-block shrink-0 ${className}`} dangerouslySetInnerHTML={{ __html: ICONS[name] ?? "" }} />;
}
