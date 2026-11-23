import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": "/src" } },
  /* 로컬 FastAPI(:8000)의 /api/v1 계약으로 보낸다. */
  server: { host: "127.0.0.1", proxy: { "/api/v1": "http://127.0.0.1:8000" } },
});
