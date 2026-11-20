import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": "/src" } },
  /* 모의 API(contracts/mock_api, :8000)로 보낸다. MSW는 옛 /api/cards만 맡는다 */
  server: { host: "127.0.0.1", proxy: { "/api/v1": "http://127.0.0.1:8000" } },
});
