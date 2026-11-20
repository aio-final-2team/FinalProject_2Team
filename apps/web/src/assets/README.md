# apps/web/src/assets

React 화면에서 import해 쓰는 공통 정적 에셋을 둡니다. Vite가 빌드 시 해시 파일명으로 처리합니다.

## logo/

유치온 메인 로고(배지 캐릭터 + 눈동자 "유치온", 가로형, 560×220)입니다. 앱 상단 등 대표 로고는 이것을 씁니다.

| 파일 | 용도 |
|---|---|
| `yuchion-main-logo-on-blue.svg` / `yuchion-main-logo-transparent.svg` | 브랜드(블루 #2F5BEA) 배경 |
| `yuchion-main-logo-light.svg` / `yuchion-main-logo-light-transparent.svg` | 일반 모드(흰 배경, 네이비 글자) |
| `yuchion-main-logo-dark.svg` / `yuchion-main-logo-dark-transparent.svg` | 다크 모드(#0E1424, 흰 글자) |

```jsx
import logo from "./assets/logo/yuchion-main-logo-light-transparent.svg";

<img src={logo} alt="유치온" />
```


## brand · icons

- `brand/`: 말풍선 친구 표정 8종(학부모 화면 전용, `flat/`은 32px 이하용), '온' 심볼과 단색 심볼(교사·원장 화면 전용), 워드마크, 앱 시작 로고 모션 모듈 `yuchion-logo-motion.js`.
- `icons/`: 24px 선 아이콘 20종. `components/Icon.tsx`가 이름으로 불러 쓴다.
- 원본: `유치온_에셋_최종/01_브랜드에셋`
