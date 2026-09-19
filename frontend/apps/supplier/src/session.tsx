import { HubSession } from "@sanovio/api";
import { SignIn } from "@sanovio/ui";
import { useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { SessionContext, type Signed } from "./sessionContext";

/** The supplier signs in at the hub; the token lives in this component's state only (§20). */
export function SessionGate({ hubUrl, children }: { hubUrl: string; children: ReactNode }) {
  const queries = useQueryClient();
  const [signed, setSigned] = useState<Signed | null>(null);

  async function signIn(email: string, password: string) {
    const session = new HubSession({ baseUrl: hubUrl });
    await session.signIn(email, password);
    const me = await session.call((hub) => hub.GET("/api/v1/auth/me"));
    setSigned({
      session,
      me,
      signOut: () => {
        session.signOut();
        queries.clear();
        setSigned(null);
      },
    });
  }

  if (!signed) {
    return <SignIn title="Supplier sign-in" hint="Your catalog team account." onSignIn={signIn} />;
  }
  return <SessionContext value={signed}>{children}</SessionContext>;
}
