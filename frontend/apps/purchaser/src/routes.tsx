import type { RouteObject } from "react-router";

import { ArticlePage } from "./articles/ArticlePage";
import { ArticlesPage } from "./articles/ArticlesPage";
import { AssessmentPage } from "./assessments/AssessmentPage";
import { AssessmentsPage } from "./assessments/AssessmentsPage";
import { Layout } from "./Layout";

export const routes: RouteObject[] = [
  {
    element: <Layout />,
    children: [
      { path: "/", element: <AssessmentsPage /> },
      { path: "/articles", element: <ArticlesPage /> },
      { path: "/articles/:articleId", element: <ArticlePage /> },
      { path: "/assessments/:assessmentId", element: <AssessmentPage /> },
    ],
  },
];
