import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

import { ApiError } from "./errors";
import { HubSession, PurchaserSession } from "./session";

const NODE = "http://node.test";
const HUB = "http://hub.test";

const state = { exchanges: 0, expiredCalls: 0, installed: [] as unknown[] };

const server = setupServer(
  http.post(`${NODE}/api/v1/auth/login`, () =>
    HttpResponse.json({ access_token: "node-token", expires_at: "2026-09-19T17:00:00Z" }),
  ),
  http.post(`${NODE}/api/v1/hub-assertions`, ({ request }) =>
    request.headers.get("Authorization") === "Bearer node-token"
      ? HttpResponse.json({ assertion: `assertion-${state.exchanges}` })
      : HttpResponse.json({ detail: "not signed in" }, { status: 401 }),
  ),
  http.post(`${HUB}/api/v1/auth/token-exchange`, () => {
    state.exchanges += 1;
    return HttpResponse.json({
      access_token: `hub-${state.exchanges}`,
      expires_at: "2026-09-19T09:30:00Z",
      tenant_alias: "Hospital H-7F3A",
    });
  }),
  http.get(`${HUB}/api/v1/auth/me`, ({ request }) => {
    if (state.expiredCalls > 0) {
      state.expiredCalls -= 1;
      return HttpResponse.json({ detail: "invalid or expired token" }, { status: 401 });
    }
    return HttpResponse.json({ kind: "purchaser", token: request.headers.get("Authorization") });
  }),
  http.get(`${HUB}/api/v1/templates`, () =>
    HttpResponse.json([
      { code: "syringe", definition: { code: "syringe" }, updated_at: "2026-09-19T10:00:00Z" },
      { code: "needle", definition: { code: "needle" }, updated_at: "2026-09-17T09:00:00Z" },
    ]),
  ),
  http.get(`${NODE}/api/v1/templates`, () =>
    HttpResponse.json([
      { code: "syringe", updated_at: "2026-09-17T09:00:00Z" },
      { code: "needle", updated_at: "2026-09-17T09:00:00Z" },
    ]),
  ),
  http.put(`${NODE}/api/v1/templates`, async ({ request }) => {
    state.installed.push(await request.json());
    return HttpResponse.json({});
  }),
  http.post(`${HUB}/api/v1/assessments/:id/send-questions`, () =>
    HttpResponse.json(
      { detail: "attribute proposals are still running", code: "ATTRIBUTE_PROPOSAL_PENDING" },
      { status: 409 },
    ),
  ),
);

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
});
afterAll(() => {
  server.close();
});
beforeEach(() => {
  Object.assign(state, { exchanges: 0, expiredCalls: 0, installed: [] });
});

async function signedIn(): Promise<PurchaserSession> {
  const session = new PurchaserSession({ baseUrl: NODE }, { baseUrl: HUB });
  await session.signIn("anna.meier@demo-ksp.example", "pw");
  return session;
}

test("signing in logs in at the node and exchanges an assertion at the hub", async () => {
  const session = new PurchaserSession({ baseUrl: NODE }, { baseUrl: HUB });

  const exchanged = await session.signIn("anna.meier@demo-ksp.example", "pw");

  expect(exchanged.tenant_alias).toBe("Hospital H-7F3A");
  expect(session.signedIn).toBe(true);
});

test("an expired hub session is exchanged again once, silently", async () => {
  const session = await signedIn();
  state.expiredCalls = 1;

  const me = await session.atHub((hub) => hub.GET("/api/v1/auth/me"));

  expect(me).toMatchObject({ token: "Bearer hub-2" });
  expect(state.exchanges).toBe(2);
});

test("a second refusal is raised as an ApiError", async () => {
  const session = await signedIn();
  state.expiredCalls = 2;

  const refused = session.atHub((hub) => hub.GET("/api/v1/auth/me"));

  await expect(refused).rejects.toMatchObject({ status: 401 });
  expect(state.exchanges).toBe(2);
});

test("a conflict carries its code", async () => {
  const session = await signedIn();

  const error: unknown = await session
    .atHub((hub) =>
      hub.POST("/api/v1/assessments/{assessment_id}/send-questions", {
        params: { path: { assessment_id: "a1" } },
        body: { version: 3 },
      }),
    )
    .catch((caught: unknown) => caught);

  expect(error).toBeInstanceOf(ApiError);
  expect((error as ApiError).code).toBe("ATTRIBUTE_PROPOSAL_PENDING");
  expect((error as ApiError).message).toBe("attribute proposals are still running");
});

test("only newer hub definitions are installed at the node", async () => {
  const session = await signedIn();

  expect(await session.syncTemplates()).toEqual(["syringe"]);
  expect(state.installed).toEqual([
    { definition: { code: "syringe" }, updated_at: "2026-09-19T10:00:00Z" },
  ]);
});

test("signing out forgets both tokens", async () => {
  const session = await signedIn();

  session.signOut();

  expect(session.signedIn).toBe(false);
});

test("a supplier signs in at the hub only", async () => {
  server.use(
    http.post(`${HUB}/api/v1/auth/login`, () =>
      HttpResponse.json({ access_token: "bd-token", expires_at: "2026-09-19T17:00:00Z" }),
    ),
  );
  const session = new HubSession({ baseUrl: HUB });

  await session.signIn("catalog@bd-demo.example", "pw");

  expect(session.signedIn).toBe(true);
});
