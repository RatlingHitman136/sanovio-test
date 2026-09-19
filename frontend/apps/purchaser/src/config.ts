/**
 * Where the two services are. The node serves this app, so it is always this origin; the hub
 * address comes from the node at runtime (§20), so one build fits every hospital. In
 * development Vite proxies `/hub` to the hub instead.
 */
export interface Endpoints {
  node: string;
  hub: string;
}

export async function resolveEndpoints(origin: string, dev: boolean): Promise<Endpoints> {
  if (dev) return { node: origin, hub: `${origin}/hub` };
  const response = await fetch(`${origin}/api/v1/client-config`);
  if (!response.ok) throw new Error(`the node gave no client config (${response.status})`);
  const config = (await response.json()) as { hub_url: string };
  return { node: origin, hub: config.hub_url.replace(/\/$/, "") };
}
