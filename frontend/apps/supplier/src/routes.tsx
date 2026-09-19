import type { RouteObject } from "react-router";

import { CatalogPage } from "./catalog/CatalogPage";
import { FamilyPage } from "./catalog/FamilyPage";
import { Layout } from "./Layout";
import { InboxPage } from "./requests/InboxPage";
import { RequestPage } from "./requests/RequestPage";

export const routes: RouteObject[] = [
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
