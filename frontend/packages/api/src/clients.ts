import createClient, { type Client, type Middleware } from "openapi-fetch";

import type { paths as HubPaths } from "./generated/hub";
import type { paths as NodePaths } from "./generated/node";

export type NodeClient = Client<NodePaths>;
export type HubClient = Client<HubPaths>;

/** A bearer token held in memory only: never in localStorage or a cookie (§20). */
export class TokenHolder {
  token: string | undefined;
}

function bearer(holder: TokenHolder): Middleware {
  return {
    onRequest({ request }) {
      if (holder.token) request.headers.set("Authorization", `Bearer ${holder.token}`);
      return request;
    },
  };
}

export interface ClientOptions {
  baseUrl: string;
  fetch?: typeof fetch;
}

export function nodeClient(options: ClientOptions, holder: TokenHolder): NodeClient {
  const client = createClient<NodePaths>(options);
  client.use(bearer(holder));
  return client;
}

export function hubClient(options: ClientOptions, holder: TokenHolder): HubClient {
  const client = createClient<HubPaths>(options);
  client.use(bearer(holder));
  return client;
}
