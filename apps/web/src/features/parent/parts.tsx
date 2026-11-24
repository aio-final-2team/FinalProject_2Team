import { Link, type LinkProps } from "react-router";

/** 주 버튼 모양의 링크 (디자인 시스템 7.1: 높이 52, 모서리 8, 브랜드 블루 채움) */
export function PrimaryLink(props: LinkProps) {
  return <Link {...props} className="flex h-[52px] w-full items-center justify-center rounded-md bg-brand-fill text-body font-semibold text-on-brand active:scale-[.97]" />;
}
