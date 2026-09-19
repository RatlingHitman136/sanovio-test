import type { HubSchemas, HubSession } from "@sanovio/api";
import { createContext, use } from "react";

type Me = HubSchemas["schemas"]["Me"];

export interface Signed {
  session: HubSession;
  me: Me;
  signOut: () => void;
}

export const SessionContext = createContext<Signed | null>(null);

export function useSession(): Signed {
  const signed = use(SessionContext);
  if (!signed) throw new Error("useSession outside a signed-in session");
  return signed;
}
