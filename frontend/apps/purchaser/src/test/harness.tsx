import { PurchaserSession } from "@sanovio/api";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { http, HttpResponse, type HttpHandler } from "msw";
import { setupServer } from "msw/node";
import { RouterProvider, createMemoryRouter } from "react-router";

import { routes } from "../routes";
import { SessionContext } from "../sessionContext";
import { HUB, NODE, me, templates } from "./fixtures";

/** Node and hub as MSW handlers; each test adds what its screen calls. */
export const server = setupServer(
  http.post(`${NODE}/api/v1/auth/login`, () =>
    HttpResponse.json({ access_token: "node-token", expires_at: "2026-09-19T17:00:00Z" }),
  ),
  http.post(`${NODE}/api/v1/hub-assertions`, () =>
    HttpResponse.json({ assertion: "signed", jti: "j", expires_at: "2026-09-19T09:05:00Z" }),
  ),
  http.post(`${HUB}/api/v1/auth/token-exchange`, () =>
    HttpResponse.json({
      access_token: "hub-token",
      expires_at: "2026-09-19T09:30:00Z",
      tenant_alias: "Hospital H-7F3A",
    }),
  ),
  http.get(`${NODE}/api/v1/templates`, () => HttpResponse.json(templates)),
);

export function serve(...handlers: HttpHandler[]): void {
  server.use(...handlers);
}

/** The purchaser app at `path`, signed in, against the MSW node and hub. */
export async function renderPurchaser(path: string) {
  const session = new PurchaserSession({ baseUrl: NODE }, { baseUrl: HUB });
  const hub = await session.signIn(me.email, "pw");
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const queries = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queries}>
      <SessionContext value={{ session, me, hub, signOut: () => undefined }}>
        <RouterProvider router={router} />
      </SessionContext>
    </QueryClientProvider>,
  );
  return { router, session };
}
