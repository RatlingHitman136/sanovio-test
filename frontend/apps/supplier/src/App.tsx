import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider, createBrowserRouter } from "react-router";

import { routes } from "./routes";
import { SessionGate } from "./session";

/** Served by the hub, so the hub is this origin (§20). */
export function App({ hubUrl }: { hubUrl: string }) {
  const [queries] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 5_000 } } }),
  );
  const [router] = useState(() => createBrowserRouter(routes));
  return (
    <QueryClientProvider client={queries}>
      <SessionGate hubUrl={hubUrl}>
        <RouterProvider router={router} />
      </SessionGate>
    </QueryClientProvider>
  );
}
