import { createContext, useContext, type ReactNode } from "react";

/** 알림장 탭 안에서 두 화면이 같은 제목과 칸 전환 줄을 쓰도록 넘겨 주는 값 */
export const NotebookCtx = createContext<{ title: string; top: ReactNode } | null>(null);
export const useNotebook = () => useContext(NotebookCtx);
