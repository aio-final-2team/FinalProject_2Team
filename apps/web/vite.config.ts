import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig(({ mode }) => {
  /* 개발 서버가 /api/v1을 보낼 백엔드. 비우면 로컬 FastAPI(:8000), 팀 서버 주소를 넣으면 진짜 DB·AI 응답을 받는다.
     VITE_로 시작하지 않는 이름이라 화면 번들에는 들어가지 않는다(README '진짜 응답 보면서 개발하기'). */
  const target = loadEnv(mode, ".", "").API_PROXY_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react(), tailwindcss()],
    resolve: { alias: { "@": "/src" } },
    server: { host: "127.0.0.1", proxy: { "/api/v1": { target, changeOrigin: true } } },
  };
});
