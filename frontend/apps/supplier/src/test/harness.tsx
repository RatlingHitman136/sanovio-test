import { HubSession } from "@sanovio/api";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { http, HttpResponse, type HttpHandler } from "msw";
import { setupServer } from "msw/node";
import { RouterProvider, createMemoryRouter } from "react-router";

import { routesFor } from "../routes";
import { SessionContext } from "../sessionContext";

export const HUB = "http://hub.test";

export const server = setupServer(
  http.post(`${HUB}/api/v1/auth/login`, () =>
    HttpResponse.json({ access_token: "bd-token", expires_at: "2026-09-19T17:00:00Z" }),
  ),
);

export function serve(...handlers: HttpHandler[]): void {
  server.use(...handlers);
}

const PEOPLE = {
  SUPPLIER: { kind: "supplier", display_name: "BD Catalog", organization: "BD" },
  OPERATOR: { kind: "operator", display_name: "Hub Operator", organization: "Sanovio Operations" },
} as const;

export function renderSupplier(path: string) {
  return renderAs("SUPPLIER", path);
}

export function renderOperator(path: string) {
  return renderAs("OPERATOR", path);
}

async function renderAs(role: keyof typeof PEOPLE, path: string) {
  const session = new HubSession({ baseUrl: HUB });
  await session.signIn("someone@hub.example", "pw");
  const me = { ...PEOPLE[role], role };
  const router = createMemoryRouter(routesFor(role), { initialEntries: [path] });
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <SessionContext value={{ session, me, signOut: () => undefined }}>
        <RouterProvider router={router} />
      </SessionContext>
    </QueryClientProvider>,
  );
  return router;
}
