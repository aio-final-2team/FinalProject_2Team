import { useId } from "react";
import basic from "@/assets/brand/buddy-basic.svg";
import processing from "@/assets/brand/buddy-processing.svg";
import done from "@/assets/brand/buddy-done.svg";
import check from "@/assets/brand/buddy-check.svg";
import guide from "@/assets/brand/buddy-guide.svg";
import sorry from "@/assets/brand/buddy-sorry.svg";
import waiting from "@/assets/brand/buddy-waiting.svg";
import hello from "@/assets/brand/buddy-hello.svg";

const flat = import.meta.glob("../assets/brand/flat/*.svg", { eager: true, import: "default" }) as Record<string, string>;
const flatOf = (face: string) => flat[`../assets/brand/flat/buddy-flat-${face}.svg`];
import wordNavy from "@/assets/brand/wordmark-navy.svg";
import wordWhite from "@/assets/brand/wordmark-white.svg";
import mainLight from "@/assets/logo/yuchion-main-logo-light-transparent.svg";
import mainDark from "@/assets/logo/yuchion-main-logo-dark-transparent.svg";
import mainOnBlue from "@/assets/logo/yuchion-main-logo-transparent.svg";

/** 말풍선 친구: 학부모 화면에서만 쓴다. 표정 = 서비스 상태 (에셋 README) */
const BUDDY = { basic, processing, done, check, guide, sorry, waiting, hello } as const;
export type Expression = keyof typeof BUDDY;

/** small: 32px 이하에서는 유리 광택이 뭉개지므로 평면(flat) 버전을 쓴다 */
export function Buddy({ face, className = "size-24", small }: { face: Expression; className?: string; small?: boolean }) {
  return <img src={small ? flatOf(face) : BUDDY[face]} alt="" className={className} draggable={false} />;
}

/** '온' 심볼: 교사·원장 화면에서만 쓴다. 눈과 눈동자를 나눠 깜빡임·훑기 모션을 줄 수 있다. */
export function SymbolMark({ motion, className = "size-14" }: { motion?: "blink" | "blink2" | "scan" | "scan2" | "closed" | "curious"; className?: string }) {
  const id = useId();
  return (
    <svg viewBox="0 0 120 120" aria-hidden className={`sym ${motion ? `sym-${motion}` : ""} rounded-[28%] ${className}`}>
      <defs>
        <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#3D63F2" />
          <stop offset="1" stopColor="#2440C8" />
        </linearGradient>
      </defs>
      <rect rx="28" width="120" height="120" fill={`url(#${id})`} />
      <g transform="translate(14 16) scale(.92)">
        <path d="M50 43 V50 M10 50 H90 M22 66 V90 H86" stroke="#fff" strokeWidth="16" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        <g className="eye">
          <circle cx="50" cy="20" r="16" fill="#fff" stroke="#fff" strokeWidth="12.5" />
          <g className="pupil">
            <circle cx="44" cy="21" r="7.2" fill="#0B1F3A" />
            <circle cx="46.4" cy="18" r="2.1" fill="#fff" />
          </g>
        </g>
      </g>
    </svg>
  );
}

export function Wordmark({ className = "h-[18px]" }: { className?: string }) {
  return (
    <>
      <img src={wordNavy} alt="유치온" className={`${className} w-auto dark:hidden`} />
      <img src={wordWhite} alt="유치온" className={`${className} hidden w-auto dark:inline`} />
    </>
  );
}

/** 앱 인트로와 같은 유치온 대표 로고. 모든 화면 상단은 이 로고를 기본으로 쓴다. */
export function MainLogo({ className = "h-8", onBlue = false }: { className?: string; onBlue?: boolean }) {
  if (onBlue) return <img src={mainOnBlue} alt="유치온" className={`${className} w-auto`} />;
  return (
    <>
      <img src={mainLight} alt="유치온" className={`${className} w-auto dark:hidden`} />
      <img src={mainDark} alt="유치온" className={`${className} hidden w-auto dark:inline`} />
    </>
  );
}
