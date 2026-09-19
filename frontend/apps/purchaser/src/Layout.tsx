import { AppShell } from "@sanovio/ui";
import { Link, Outlet, useLocation } from "react-router";

import { useSession } from "./sessionContext";

export function Layout() {
  const { me, hub, signOut } = useSession();
  const { pathname } = useLocation();
  const nav = [
    { to: "/", label: "Assessments", active: pathname === "/" || pathname.startsWith("/assess") },
    { to: "/articles", label: "Articles", active: pathname.startsWith("/articles") },
  ];
  return (
    <AppShell
      product="Sanovio · Purchaser"
      who={`${me.display_name} · ${hub.tenant_alias}`}
      nav={nav}
      onSignOut={signOut}
      renderLink={(item, className) => (
        <Link to={item.to} className={className}>
          {item.label}
        </Link>
      )}
    >
      <Outlet />
    </AppShell>
  );
}
