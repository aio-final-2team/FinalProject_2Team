import React from "react";
import { createRoot } from "react-dom/client";

function App() {
  return (
    <main>
      <h1>유치온</h1>
      <p>학부모와 교직원의 요청·상담·알림장을 연결하는 앱 화면 골격입니다.</p>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
