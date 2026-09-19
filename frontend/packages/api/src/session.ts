import {
  hubClient,
  nodeClient,
  TokenHolder,
  type ClientOptions,
  type HubClient,
  type NodeClient,
} from "./clients";
import { unwrap } from "./errors";
import type { components as Hub } from "./generated/hub";

type Outcome<T> = { data?: T; error?: unknown; response: Response };
export type ExchangeResponse = Hub["schemas"]["ExchangeResponse"];

/**
 * The purchaser's two sessions at once (§19 step 0), like the demo client's `Session`:
 * a node login, then a node assertion exchanged for a hub session. The hub issues no refresh
 * token, so an expired hub session is renewed with a fresh assertion, once, silently.
 */
export class PurchaserSession {
  readonly node: NodeClient;
  readonly hub: HubClient;
  private readonly nodeToken = new TokenHolder();
  private readonly hubToken = new TokenHolder();

  constructor(node: ClientOptions, hub: ClientOptions) {
    this.node = nodeClient(node, this.nodeToken);
    this.hub = hubClient(hub, this.hubToken);
  }

  get signedIn(): boolean {
    return this.nodeToken.token !== undefined && this.hubToken.token !== undefined;
  }

  async signIn(email: string, password: string): Promise<ExchangeResponse> {
    const login = unwrap(await this.node.POST("/api/v1/auth/login", { body: { email, password } }));
    this.nodeToken.token = login.access_token;
    return this.exchange();
  }

  signOut(): void {
    this.nodeToken.token = undefined;
    this.hubToken.token = undefined;
  }

  /** A node call; its data, or an ApiError. */
  async atNode<T>(call: (node: NodeClient) => Promise<Outcome<T>>): Promise<T> {
    return unwrap(await call(this.node));
  }

  /** A hub call, renewed once if the hub session has expired. */
  async atHub<T>(call: (hub: HubClient) => Promise<Outcome<T>>): Promise<T> {
    let outcome = await call(this.hub);
    if (outcome.response.status === 401 && this.nodeToken.token) {
      await this.exchange();
      outcome = await call(this.hub);
    }
    return unwrap(outcome);
  }

  /** Installs every hub definition newer than the node's copy (§7.2, D52). */
  async syncTemplates(): Promise<string[]> {
    const installed = await this.atNode((node) => node.GET("/api/v1/templates"));
    const served = await this.atHub((hub) => hub.GET("/api/v1/templates"));
    const local = new Map(installed.map((row) => [row.code, Date.parse(row.updated_at)]));
    const synced: string[] = [];
    for (const template of served) {
      const ours = local.get(template.code);
      if (ours !== undefined && ours >= Date.parse(template.updated_at)) continue;
      await this.atNode((node) =>
        node.PUT("/api/v1/templates", {
          body: { definition: template.definition, updated_at: template.updated_at },
        }),
      );
      synced.push(template.code);
    }
    return synced;
  }

  private async exchange(): Promise<ExchangeResponse> {
    const assertion = await this.atNode((node) => node.POST("/api/v1/hub-assertions"));
    const exchanged = unwrap(
      await this.hub.POST("/api/v1/auth/token-exchange", {
        body: { assertion: assertion.assertion },
      }),
    );
    this.hubToken.token = exchanged.access_token;
    return exchanged;
  }
}

/** A supplier (or operator) signed in at the hub only. */
export class HubSession {
  readonly hub: HubClient;
  private readonly token = new TokenHolder();

  constructor(hub: ClientOptions) {
    this.hub = hubClient(hub, this.token);
  }

  get signedIn(): boolean {
    return this.token.token !== undefined;
  }

  async signIn(email: string, password: string): Promise<void> {
    const login = unwrap(await this.hub.POST("/api/v1/auth/login", { body: { email, password } }));
    this.token.token = login.access_token;
  }

  signOut(): void {
    this.token.token = undefined;
  }

  async call<T>(call: (hub: HubClient) => Promise<Outcome<T>>): Promise<T> {
    return unwrap(await call(this.hub));
  }
}
