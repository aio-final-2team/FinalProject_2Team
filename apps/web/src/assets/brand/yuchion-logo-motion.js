/**
 * 유치온 로고 모션 · 앱 시작용 (B안: 점 → 두 눈 → 유·치·온 → 말풍선 친구)
 *
 * - 한 번만 재생하고 약 3.4초에 끝난다. 끝나면 onDone()을 부른다.
 * - 움직임 줄이기 설정이면 바로 최종 로고를 그리고 끝낸다.
 * - 화면을 누르면 건너뛰게 하려면 반환된 skip()을 부른다.
 * - 흰 글자 로고라서 블루 바탕(#2F5BEA, 그라데이션 #3D63F2→#2440C8) 위에 올린다.
 *
 * 사용:
 *   import { mountLogoMotion } from "./yuchion-logo-motion.js";
 *   const { skip, destroy } = mountLogoMotion(svgElement, { onDone: () => showLogin() });
 *   // svgElement는 <svg viewBox="40 40 560 280"> 같은 빈 SVG
 *
 * 원본 미리보기: 유치온_로고모션_최종.html (A안·B안 5.2초 반복)
 */

const END = 3.4;
const NV = "#0B1F3A";
const SW = 'stroke="#fff" stroke-width="16" fill="none" stroke-linecap="round" stroke-linejoin="round"';
const YU = `<path d="M10 62 H90 M33 62 V90 M67 62 V90" ${SW}/>`;
const CHI = `<circle cx="31" cy="6" r="9.6" fill="#fff"/><path d="M10 30 H52 M31 30 L11 88 M33 54 L54 88 M84 4 V96" ${SW}/>`;
const ON = `<path d="M50 43 V50 M10 50 H90 M22 66 V90 H86" ${SW}/>`;
const BODY = "M64 20 C90 20 103 40 101 64 C99 87 85 101 66 101 C60 101 56 99 52 96 C48 100 42 102 36 100 C29 98 27 92 29 86 C21 80 17 70 19 58 C22 35 41 20 64 20 Z";

let uid = 0;

function buddy(p) {
  return `<svg x="70" y="80" width="200" height="200" viewBox="0 0 120 120"><defs>
<linearGradient id="${p}b" x1=".35" y1="0" x2=".55" y2="1"><stop offset="0" stop-color="#A8A3F4"/><stop offset=".45" stop-color="#7590F0"/><stop offset=".8" stop-color="#4F5CF2"/><stop offset="1" stop-color="#3B3FEA"/></linearGradient>
<radialGradient id="${p}o" cx=".35" cy=".3" r=".8"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".45" stop-color="#B8F3E2"/><stop offset="1" stop-color="#3FCFAE"/></radialGradient></defs>
<g transform="rotate(-6 60 60)"><path d="${BODY}" fill="url(#${p}b)"/><path d="${BODY}" fill="none" stroke="#fff" stroke-opacity=".45" stroke-width="1.4"/>
<g transform="rotate(6 60 60)"><g fill="#fff" fill-opacity=".82"><rect x="61" y="42" width="7.5" height="15" rx="3.75" transform="rotate(-8 64.7 49.5)"/><rect x="74" y="41" width="7.5" height="15" rx="3.75" transform="rotate(-8 77.7 48.5)"/></g>
<path d="M52 64 Q61 73 72 66" stroke="#fff" stroke-opacity=".82" stroke-width="5.2" fill="none" stroke-linecap="round"/></g></g>
<circle cx="98" cy="22" r="8" fill="url(#${p}o)"/><circle cx="95.6" cy="19.6" r="2.3" fill="#fff"/></svg>`;
}

function scene(p) {
  return `<defs><radialGradient id="${p}gl"><stop offset="0" stop-color="#9BF0D6" stop-opacity=".75"/><stop offset="1" stop-color="#9BF0D6" stop-opacity="0"/></radialGradient></defs>
<g id="${p}bud" opacity="0"><circle cx="170" cy="182" r="108" fill="#fff" opacity=".14"/><circle cx="170" cy="182" r="84" fill="#fff" opacity=".9"/>${buddy(p)}</g>
<g id="${p}word">
 <g id="${p}yu">${YU}<circle cx="50" cy="25" r="17" fill="none" stroke="#fff" stroke-width="12.5"/><g id="${p}yuP" opacity="0"><circle cx="50" cy="25" r="17" fill="#fff"/><circle cx="56" cy="26" r="7.6" fill="${NV}"/><circle cx="58.4" cy="23" r="2.2" fill="#fff"/></g></g>
 <g id="${p}chi">${CHI}</g>
 <g id="${p}on">${ON}<circle cx="50" cy="20" r="16" fill="none" stroke="#fff" stroke-width="12.5"/><g id="${p}onP" opacity="0"><circle cx="50" cy="20" r="16" fill="#fff"/><circle cx="44" cy="21" r="7.2" fill="${NV}"/><circle cx="46.4" cy="18" r="2.1" fill="#fff"/></g></g>
</g>
<g id="${p}eyes" opacity="0"><g id="${p}eL"><circle r="23" fill="#fff"/><circle cx="6" r="10" fill="${NV}"/></g><g id="${p}eR"><circle r="23" fill="#fff"/><circle cx="6" r="10" fill="${NV}"/></g></g>
<circle id="${p}glow" cx="320" cy="180" r="70" fill="url(#${p}gl)" opacity="0"/>
<g id="${p}dot"><circle r="9" fill="#5BE0BC"/><circle cx="-2.6" cy="-2.6" r="2.8" fill="#fff" opacity=".9"/></g>`;
}

const cl = (x) => Math.max(0, Math.min(1, x));
const lin = (t, a, b) => cl((t - a) / (b - a));
const eo = (x) => 1 - Math.pow(1 - x, 3);
const back = (x) => 1 + 2.9 * Math.pow(x - 1, 3) + 1.9 * Math.pow(x - 1, 2);
const lerp = (a, b, x) => a + (b - a) * x;
const pop = (t, a, d = 0.35) => {
  const x = lin(t, a, a + d);
  return x <= 0 ? 0 : back(x);
};

export function mountLogoMotion(svg, { onDone } = {}) {
  const p = `ylm${uid++}`;
  svg.innerHTML = scene(p);
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "유치온");
  const $ = (id) => svg.querySelector(`#${p}${id}`);
  const set = (id, k, v) => $(id).setAttribute(k, v);
  const tr = (id, x, y, sx, sy = sx) => set(id, "transform", `translate(${x} ${y}) scale(${sx} ${sy})`);
  const X0 = 170, Y0 = 128;
  const sq = (id, x, t, t0) => {
    const v = pop(t, t0), q = Math.sin(Math.PI * lin(t, t0, t0 + 0.5)) * 0.12;
    tr(id, x, Y0, v * (1 + q), v * (1 - q));
    set(id, "opacity", v > 0 ? 1 : 0);
  };

  function draw(t) {
    set("glow", "opacity", lin(t, 0.1, 0.5) * (1 - lin(t, 0.8, 1.0)));
    tr("dot", 320, 180, 1 + 0.15 * Math.sin(t * 9) * (t < 0.8 ? 1 : 0));
    set("dot", "opacity", t < 0.85 ? lin(t, 0, 0.25) : 0);
    const sp = eo(lin(t, 0.8, 1.2)), blink = t > 1.35 && t < 1.45 ? 0.15 : 1, mv = eo(lin(t, 1.6, 2.0));
    set("eyes", "opacity", t > 0.8 && t < 2.05 ? 1 : 0);
    set("eL", "transform", `translate(${lerp(lerp(320, 248, sp), X0 + 50, mv)} ${lerp(180, Y0 + 25, mv)}) scale(${t < 1.6 ? sp * blink : lerp(1, 0.74, mv)})`);
    set("eR", "transform", `translate(${lerp(lerp(320, 392, sp), X0 + 250, mv)} ${lerp(180, Y0 + 20, mv)}) scale(${t < 1.6 ? sp * blink : lerp(1, 0.7, mv)}) scale(-1 1)`);
    sq("yu", X0, t, 1.95);
    sq("chi", X0 + 100, t, 2.15);
    sq("on", X0 + 200, t, 2.35);
    set("yuP", "opacity", t > 1.95 ? 1 : 0);
    set("onP", "opacity", t > 2.0 ? 1 : 0);
    const u = eo(lin(t, 2.8, 3.3));
    set("word", "transform", `translate(${lerp(0, 112, u)} ${lerp(0, 8, u)}) scale(${lerp(1, 0.92, u)})`);
    const b = pop(t, 2.9, 0.45);
    set("bud", "opacity", cl(b));
    set("bud", "transform", `translate(170 182) scale(${b}) translate(-170 -182)`);
  }

  let raf = 0, done = false;
  const finish = () => {
    if (done) return;
    done = true;
    cancelAnimationFrame(raf);
    draw(END + 0.5);
    onDone?.();
  };
  const reduce = typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) {
    draw(END + 0.5);
    setTimeout(finish, 400);
  } else {
    draw(0);
    const t0 = performance.now();
    const loop = (now) => {
      const t = (now - t0) / 1000;
      if (t >= END) return finish();
      draw(t);
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
  }
  return { skip: finish, destroy: () => cancelAnimationFrame(raf) };
}
