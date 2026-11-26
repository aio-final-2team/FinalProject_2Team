import { Link } from "react-router";
import { Icon } from "./Icon";

/**
 * 화면 맨 위 '뒤로' 링크. 선생님 화면은 전부 이 모양 하나만 쓴다.
 * 높이 44(누르기 편한 크기), 아이콘 20, 글자 굵기 500, 브랜드 블루(accent). 위치는 화면 위 8px 아래에서 시작한다.
 */
export function BackLink({ to, label, className = "", onClick }: { to: string; label: string; className?: string; onClick?: (e: React.MouseEvent<HTMLAnchorElement>) => void }) {
  return (
    <Link to={to} onClick={onClick} className={`inline-flex min-h-11 items-center gap-0.5 self-start text-body font-medium text-accent ${className}`}>
      <Icon name="chevL" className="size-5" />
      {label}
    </Link>
  );
}
