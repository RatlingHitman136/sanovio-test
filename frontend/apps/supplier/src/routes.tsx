import type { RouteObject } from "react-router";

import { CatalogPage } from "./catalog/CatalogPage";
import { FamilyPage } from "./catalog/FamilyPage";
import { Layout } from "./Layout";
import { operatorRoutes } from "./operator/routes";
import { InboxPage } from "./requests/InboxPage";
import { RequestPage } from "./requests/RequestPage";

export const supplierRoutes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { path: "/", element: <InboxPage /> },
      { path: "/requests/:assessmentId", element: <RequestPage /> },
      { path: "/catalog", element: <CatalogPage /> },
      { path: "/catalog/:familyId", element: <FamilyPage /> },
    ],
  },
];

/** One app at the hub, two roles: each sees only its own pages (§20). */
export function routesFor(role: string | null | undefined): RouteObject[] {
  return role === "OPERATOR" ? operatorRoutes : supplierRoutes;
}
