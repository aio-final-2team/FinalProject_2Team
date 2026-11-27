import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { ThemeToggle } from "@/components/ThemeToggle";
import { ToastProvider } from "@/components/Toast";
import { SessionProvider, useSession } from "./session";

function Toasts({ children }: { children: ReactNode }) {
  const { role } = useSession();
  return <ToastProvider role={role ?? "teacher"}>{children}</ToastProvider>;
}

export function Providers({ children }: { children: ReactNode }) {
  const [qc] = useState(() => new QueryClient({ defaultOptions: { queries: { staleTime: 30_000, retry: 1 } } }));
  return (
    <QueryClientProvider client={qc}>
      <SessionProvider>
        <Toasts>{children}</Toasts>
        <ThemeToggle />
      </SessionProvider>
    </QueryClientProvider>
  );
}
