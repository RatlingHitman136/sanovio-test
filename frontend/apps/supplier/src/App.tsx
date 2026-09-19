import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { RouterProvider, createBrowserRouter } from "react-router";

import { routesFor } from "./routes";
import { SessionGate } from "./session";
import { useSession } from "./sessionContext";

/** Served by the hub, so the hub is this origin (§20). */
export function App({ hubUrl }: { hubUrl: string }) {
  const [queries] = useState(
    () => new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: 5_000 } } }),
  );
  return (
    <QueryClientProvider client={queries}>
      <SessionGate hubUrl={hubUrl}>
        <RoleRouter />
      </SessionGate>
    </QueryClientProvider>
  );
}

/** Built once per sign-in, so a supplier never has an operator route and the reverse. */
function RoleRouter() {
  const { me } = useSession();
  const [router] = useState(() => createBrowserRouter(routesFor(me.role)));
  return <RouterProvider router={router} />;
}
