import { createBrowserRouter, Navigate } from "react-router";
import { Guard } from "@/features/common/Guard";
import { InboxPage } from "@/features/inbox/InboxPage";
import { LoginPage } from "@/features/login/LoginPage";
import { NoteDetail } from "@/features/notes/NoteDetail";
import { TeacherHome } from "@/features/teacher/TeacherHome";
import { SoonPage } from "@/features/teacher/SoonPage";
import { CarePage } from "@/features/care/CarePage";
import { ClassPage } from "@/features/teacher/ClassPage";
import { FeedScreen } from "@/features/feed/FeedScreen";
import { SignupPage } from "@/features/consent/SignupPage";
import { ConsentsPage } from "@/features/consent/ConsentsPage";
import { ConsentAgreePage } from "@/features/consent/ConsentAgreePage";
import { RouteError } from "@/components/RouteError";
import { OverviewPage } from "@/features/director/OverviewPage";
import { DocumentPage } from "@/features/teacher/DocumentPage";
import { MemoryPage } from "@/features/teacher/MemoryPage";
import { TeacherNotifications } from "@/features/common/NotificationList";
import { NotebookPage } from "@/features/notes/notebook";
import { ParentHome } from "@/features/parent/ParentHome";
import { NewRequestPage } from "@/features/parent/NewRequestPage";
import { NotificationsPage } from "@/features/parent/NotificationsPage";
import { RequestDetailPage } from "@/features/parent/RequestDetailPage";
import { RequestsPage } from "@/features/parent/RequestsPage";
import { ParentLayout } from "@/layouts/ParentLayout";
import { StaffLayout } from "@/layouts/StaffLayout";
import { StateView } from "@/components/StateView";

/** 주소 목록: Docs/Step2/유치온_T12_화면지도.md 1.4 */
export const router = createBrowserRouter([
  { path: "/", element: <Navigate to="/login" replace /> },
  { path: "/login", element: <LoginPage />, errorElement: <RouteError /> },
  { path: "/signup", element: <SignupPage />, errorElement: <RouteError /> },
  { path: "/consents/agree", element: <Guard allow={["teacher", "director", "parent"]} skipConsent><ConsentAgreePage /></Guard>, errorElement: <RouteError /> },
  { path: "/consents", element: <Guard allow={["teacher", "director", "parent"]}><ConsentsPage /></Guard>, errorElement: <RouteError /> },
  {
    path: "/teacher",
    errorElement: <RouteError />,
    element: (
      <Guard allow={["teacher"]}>
        <StaffLayout role="teacher" />
      </Guard>
    ),
    children: [
      { index: true, element: <Navigate to="home" replace /> },
      { path: "home", element: <TeacherHome /> },
      { path: "records", element: <Navigate to="/teacher/notes?tab=records" replace /> },
      { path: "notifications", element: <TeacherNotifications /> },
      { path: "notes", element: <NotebookPage /> },
      { path: "notes/:noteId", element: <NoteDetail /> },
      { path: "soon/:key", element: <SoonPage /> },
      { path: "class", element: <ClassPage /> },
      { path: "class/:id", element: <DocumentPage /> },
      { path: "care", element: <CarePage /> },
      { path: "feed", element: <FeedScreen role="teacher" /> },
      { path: "memory", element: <MemoryPage /> },
      /* 문의·민원 받은함은 11/27 범위 밖(알림장과 따로). 주소만 남겨 둔다 */
      { path: "inbox", element: <InboxPage role="teacher" /> },
      { path: "inbox/:cardId", element: <InboxPage role="teacher" /> },
    ],
  },
  {
    path: "/director",
    errorElement: <RouteError />,
    element: (
      <Guard allow={["director"]}>
        <StaffLayout role="director" />
      </Guard>
    ),
    children: [
      { index: true, element: <Navigate to="overview" replace /> },
      { path: "overview", element: <OverviewPage /> },
      { path: "care", element: <CarePage role="director" /> },
      { path: "notifications", element: <TeacherNotifications role="director" /> },
      { path: "feed", element: <FeedScreen role="director" /> },
      { path: "inbox", element: <InboxPage role="director" /> },
      { path: "inbox/:cardId", element: <InboxPage role="director" /> },
    ],
  },
  {
    path: "/parent",
    errorElement: <RouteError />,
    element: (
      <Guard allow={["parent"]}>
        <ParentLayout />
      </Guard>
    ),
    children: [
      { index: true, element: <Navigate to="home" replace /> },
      { path: "home", element: <ParentHome /> },
      { path: "notifications", element: <NotificationsPage /> },
      { path: "feed", element: <FeedScreen role="parent" /> },
      { path: "album", element: <Navigate to="/parent/feed?tab=mine" replace /> },
      { path: "requests", element: <RequestsPage /> },
      { path: "requests/new", element: <NewRequestPage /> },
      { path: "requests/:requestId", element: <RequestDetailPage /> },
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
