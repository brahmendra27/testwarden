import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createBrowserRouter, RouterProvider } from "react-router-dom";
import "./index.css";
import { Layout } from "./Layout";
import { ProjectsPage } from "./pages/ProjectsPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RunListPage } from "./pages/RunListPage";
import { RunDetailPage } from "./pages/RunDetailPage";
import { TestDetailPage } from "./pages/TestDetailPage";
import { FlakyTestsPage } from "./pages/FlakyTestsPage";
import { ComparePage } from "./pages/ComparePage";
import { ApiAgentPage } from "./pages/ApiAgentPage";
import { ErrorPage } from "./pages/ErrorPage";
import { QuarantinePage } from "./pages/QuarantinePage";

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 15_000 } },
});

const router = createBrowserRouter([
  {
    element: <Layout />,
    errorElement: <ErrorPage />,
    children: [
      { path: "/", element: <ProjectsPage /> },
      { path: "/p/:slug/overview", element: <OverviewPage /> },
      { path: "/p/:slug/runs", element: <RunListPage /> },
      { path: "/p/:slug/runs/:runId", element: <RunDetailPage /> },
      { path: "/p/:slug/tests/:caseId", element: <TestDetailPage /> },
      { path: "/p/:slug/flaky", element: <FlakyTestsPage /> },
      { path: "/p/:slug/compare", element: <ComparePage /> },
      { path: "/p/:slug/api-agent", element: <ApiAgentPage /> },
      { path: "/p/:slug/quarantine", element: <QuarantinePage /> },
    ],
  },
]);

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  </React.StrictMode>
);
