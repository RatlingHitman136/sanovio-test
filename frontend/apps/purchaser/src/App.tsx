import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider, createBrowserRouter } from "react-router";

import type { Endpoints } from "./config";
import { routes } from "./routes";
import { SessionGate } from "./session";

export function App({ endpoints }: { endpoints: Endpoints }) {
  const [queries] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 5_000 } } }),
  );
  const [router] = useState(() => createBrowserRouter(routes));
  return (
    <QueryClientProvider client={queries}>
      <SessionGate endpoints={endpoints}>
        <RouterProvider router={router} />
      </SessionGate>
    </QueryClientProvider>
  );
}
