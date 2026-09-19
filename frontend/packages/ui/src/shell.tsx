/** Sign-in page and the frame around every signed-in page, for both apps. */
import { useState, type ReactNode } from "react";

import { cn } from "./cn";
import { ErrorMessage } from "./feedback";
import { Button, Card, Input, Label } from "./primitives";

interface SignInProps {
  title: string;
  hint?: ReactNode;
  onSignIn: (email: string, password: string) => Promise<void>;
}

export function SignIn({ title, hint, onSignIn }: SignInProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);

  async function submit(event: { preventDefault: () => void }) {
    event.preventDefault();
    setBusy(true);
    setError(undefined);
    try {
      await onSignIn(email, password);
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center bg-neutral-50 p-4">
      <Card className="w-full max-w-sm">
        <h1 className="mb-1 text-lg font-semibold">{title}</h1>
        {hint && <p className="mb-4 text-sm text-neutral-500">{hint}</p>}
        <form className="space-y-3" onSubmit={(event) => void submit(event)}>
          <div className="space-y-1">
            <Label htmlFor="email">Email</Label>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(event) => {
                setEmail(event.target.value);
              }}
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => {
                setPassword(event.target.value);
              }}
            />
          </div>
          <ErrorMessage error={error} />
          <Button type="submit" className="w-full" disabled={busy}>
            {busy ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      </Card>
    </main>
  );
}

export interface NavItem {
  to: string;
  label: string;
  active: boolean;
}

interface ShellProps {
  product: string;
  who: string;
  nav: NavItem[];
  onSignOut: () => void;
  renderLink: (item: NavItem, className: string) => ReactNode;
  children: ReactNode;
}

/** `renderLink` lets each app use its router's link without this package depending on it. */
export function AppShell({ product, who, nav, onSignOut, renderLink, children }: ShellProps) {
  return (
    <div className="flex min-h-screen bg-neutral-50">
      <aside className="flex w-56 shrink-0 flex-col border-r border-neutral-200 bg-white">
        <div className="px-4 py-4 text-sm font-semibold text-neutral-900">{product}</div>
        <nav className="flex flex-col gap-0.5 px-2">
          {nav.map((item) => (
            <div key={item.to}>
              {renderLink(
                item,
                cn(
                  "block rounded-md px-3 py-1.5 text-sm",
                  item.active
                    ? "bg-neutral-100 font-medium text-neutral-900"
                    : "text-neutral-600 hover:bg-neutral-50",
                ),
              )}
            </div>
          ))}
        </nav>
        <div className="mt-auto border-t border-neutral-200 p-3 text-xs text-neutral-500">
          <div className="mb-2 truncate">{who}</div>
          <Button variant="secondary" size="sm" className="w-full" onClick={onSignOut}>
            Sign out
          </Button>
        </div>
      </aside>
      <main className="min-w-0 flex-1 p-6">{children}</main>
    </div>
  );
}
