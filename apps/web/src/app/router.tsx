import { createBrowserRouter, Navigate } from "react-router";
import { Guard } from "@/features/common/Guard";
import { Later } from "@/features/common/Later";
import { InboxPage } from "@/features/inbox/InboxPage";
import { LoginPage } from "@/features/login/LoginPage";
import { NoteDetail } from "@/features/notes/NoteDetail";
import { NotesPage } from "@/features/notes/NotesPage";
import { TeacherHome } from "@/features/teacher/TeacherHome";
import { ParentLayout } from "@/layouts/ParentLayout";
import { StaffLayout } from "@/layouts/StaffLayout";
import { StateView } from "@/components/StateView";

/** 주소 목록: Docs/Step2/유치온_T12_화면지도.md 1.4 */
export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/login" replace /> },
  { path: "/login", element: <LoginPage /> },
  {
    path: "/teacher",
    element: (
      <Guard allow={["teacher"]}>
        <StaffLayout role="teacher" />
      </Guard>
    ),
    children: [
      { index: true, element: <Navigate to="home" replace /> },
      { path: "home", element: <TeacherHome /> },
      { path: "records", element: <Later audience="staff" title="오늘 기록" /> },
      { path: "notes", element: <NotesPage /> },
      { path: "notes/:noteId", element: <NoteDetail /> },
      /* 문의·민원 받은함은 11/27 범위 밖(알림장과 따로). 주소만 남겨 둔다 */
      { path: "inbox", element: <InboxPage role="teacher" /> },
      { path: "inbox/:cardId", element: <InboxPage role="teacher" /> },
    ],
  },
  {
    path: "/director",
    element: (
      <Guard allow={["director"]}>
        <StaffLayout role="director" />
      </Guard>
    ),
    children: [
      { index: true, element: <Navigate to="inbox" replace /> },
      { path: "inbox", element: <InboxPage role="director" /> },
      { path: "inbox/:cardId", element: <InboxPage role="director" /> },
    ],
  },
  {
    path: "/parent",
    element: (
      <Guard allow={["parent"]}>
        <ParentLayout />
      </Guard>
    ),
    children: [
      { index: true, element: <Navigate to="home" replace /> },
      { path: "home", element: <Later audience="parent" title="홈 피드" /> },
      { path: "requests", element: <Later audience="parent" title="요청" /> },
      { path: "requests/new", element: <Later audience="parent" title="새 요청" /> },
      { path: "requests/:requestId", element: <Later audience="parent" title="요청 상세" /> },
    ],
  },
  {
    path: "*",
    element: (
      <div className="grid min-h-full place-items-center">
        <StateView kind="forbidden" audience="staff" title="없는 화면이에요" sub="주소를 확인해 주세요" />
      </div>
    ),
  },
]);
