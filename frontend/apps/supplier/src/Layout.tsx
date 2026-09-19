import { AppShell } from "@sanovio/ui";
import { Link, Outlet, useLocation } from "react-router";

import { useSession } from "./sessionContext";

export function Layout() {
  const { me, signOut } = useSession();
  const { pathname } = useLocation();
  const nav = [
    { to: "/", label: "Requests", active: pathname === "/" || pathname.startsWith("/requests") },
    { to: "/catalog", label: "Catalog", active: pathname.startsWith("/catalog") },
  ];
  return (
    <AppShell
      product="Sanovio · Supplier"
      who={`${me.display_name} · ${me.organization}`}
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
