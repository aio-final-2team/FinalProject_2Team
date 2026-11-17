import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { Providers } from "./app/Providers";
import { router } from "./app/router";
import "./styles/index.css";

/** 실제 서버(T13)가 붙기 전에는 MSW 가짜 API를 켠다. VITE_USE_MOCK=false로 끈다. */
async function start() {
  if (import.meta.env.VITE_USE_MOCK !== "false") {
    const { worker } = await import("./mocks/browser");
    await worker.start({ onUnhandledRequest: "bypass", quiet: true });
  }
  createRoot(document.getElementById("root")!).render(
    <StrictMode>
      <Providers>
        <RouterProvider router={router} />
      </Providers>
    </StrictMode>,
  );
}
start();
