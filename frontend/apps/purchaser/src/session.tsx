import { PurchaserSession } from "@sanovio/api";
import { SignIn, Spinner } from "@sanovio/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import type { Endpoints } from "./config";
import { SessionContext, type Signed } from "./sessionContext";

/**
 * Tokens live in this component's state only (§20): a reload signs out. After signing in,
 * the node's templates are brought up to date with the hub's (§19 step 0).
 */
export function SessionGate({
  endpoints,
  children,
}: {
  endpoints: Endpoints;
  children: ReactNode;
}) {
  const queries = useQueryClient();
  const [signed, setSigned] = useState<Signed | null>(null);
  const [syncing, setSyncing] = useState(false);

  async function signIn(email: string, password: string) {
    const session = new PurchaserSession({ baseUrl: endpoints.node }, { baseUrl: endpoints.hub });
    const hub = await session.signIn(email, password);
    const me = await session.atNode((node) => node.GET("/api/v1/auth/me"));
    setSyncing(true);
    try {
      await session.syncTemplates();
    } finally {
      setSyncing(false);
    }
    setSigned({
      session,
      me,
      hub,
      signOut: () => {
        session.signOut();
        queries.clear();
        setSigned(null);
      },
    });
  }

  if (syncing) return <Spinner label="Bringing the category templates up to date…" />;
  if (!signed) {
    return (
      <SignIn
        title="Purchaser sign-in"
        hint="Your hospital account. The hub session is opened for you."
        onSignIn={signIn}
      />
    );
  }
  return <SessionContext value={signed}>{children}</SessionContext>;
}
