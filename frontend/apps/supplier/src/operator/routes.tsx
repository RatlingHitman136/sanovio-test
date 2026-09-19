import type { RouteObject } from "react-router";

import { AccountsPage } from "./AccountsPage";
import { AttributesPage } from "./AttributesPage";
import { AuditPage } from "./AuditPage";
import { OperatorCatalogPage, OperatorFamilyPage } from "./CatalogPages";
import { HospitalPage, HospitalsPage } from "./HospitalsPages";
import { JobsPage } from "./JobsPage";
import { LlmUsagePage } from "./LlmUsagePage";
import { OperatorLayout } from "./OperatorLayout";
import { OverviewPage } from "./OverviewPage";
import { ProposalsPage } from "./ProposalsPage";
import { TemplatePage, TemplatesPage } from "./TemplatesPages";

export const operatorRoutes: RouteObject[] = [
  {
    element: <OperatorLayout />,
    children: [
      { path: "/", element: <OverviewPage /> },
      { path: "/proposals", element: <ProposalsPage /> },
      { path: "/attributes", element: <AttributesPage /> },
      { path: "/templates", element: <TemplatesPage /> },
      { path: "/templates/:code", element: <TemplatePage /> },
      { path: "/hospitals", element: <HospitalsPage /> },
      { path: "/hospitals/:tenantId", element: <HospitalPage /> },
      { path: "/accounts", element: <AccountsPage /> },
      { path: "/catalog", element: <OperatorCatalogPage /> },
      { path: "/catalog/:familyId", element: <OperatorFamilyPage /> },
      { path: "/jobs", element: <JobsPage /> },
      { path: "/llm", element: <LlmUsagePage /> },
      { path: "/audit", element: <AuditPage /> },
    ],
  },
];
