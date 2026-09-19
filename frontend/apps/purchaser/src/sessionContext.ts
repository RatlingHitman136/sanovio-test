import type { ExchangeResponse, NodeSchemas, PurchaserSession } from "@sanovio/api";
import { createContext, use } from "react";

type Me = NodeSchemas["schemas"]["Me"];

export interface Signed {
  session: PurchaserSession;
  me: Me;
  hub: ExchangeResponse;
  signOut: () => void;
}

export const SessionContext = createContext<Signed | null>(null);

/** The signed-in purchaser; only used below `SessionGate`. */
export function useSession(): Signed {
  const signed = use(SessionContext);
  if (!signed) throw new Error("useSession outside a signed-in session");
  return signed;
}
