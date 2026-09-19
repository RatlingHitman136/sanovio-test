import { AppShell } from "@sanovio/ui";
import { Link, Outlet, useLocation } from "react-router";

import { useSession } from "../sessionContext";

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/proposals", label: "Curation" },
  { to: "/attributes", label: "Attributes" },
  { to: "/templates", label: "Templates" },
  { to: "/hospitals", label: "Hospitals" },
  { to: "/accounts", label: "Accounts" },
  { to: "/catalog", label: "Catalog" },
  { to: "/jobs", label: "Jobs" },
  { to: "/llm", label: "LLM usage" },
  { to: "/audit", label: "Audit" },
];

/** The operator's console: the registry, trust, accounts and the hub's health (§17.1). */
export function OperatorLayout() {
  const { me, signOut } = useSession();
  const { pathname } = useLocation();
  const nav = NAV.map((item) => ({
    ...item,
    active: item.to === "/" ? pathname === "/" : pathname.startsWith(item.to),
  }));
  return (
    <AppShell
      product="Sanovio · Operator"
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
