import { Card, CardTitle, PageHeader, Spinner, Table, Td, Th } from "@sanovio/ui";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router";

import { useSession } from "../sessionContext";
import { usd } from "./shared";

/** What needs the operator now, and how much work each hospital has: counts only (D58). */
export function OverviewPage() {
  const { session } = useSession();
  const proposals = useQuery({
    queryKey: ["admin", "proposals", "PROVISIONAL"],
    queryFn: () =>
      session.call((hub) =>
        hub.GET("/api/v1/admin/attribute-proposals", {
          params: { query: { status: "PROVISIONAL" } },
        }),
      ),
  });
  const failed = useQuery({
    queryKey: ["admin", "jobs", "FAILED", ""],
    queryFn: () =>
      session.call((hub) =>
        hub.GET("/api/v1/admin/jobs", { params: { query: { status: "FAILED" } } }),
      ),
  });
  const usage = useQuery({
    queryKey: ["admin", "llm-usage", 7],
    queryFn: () =>
      session.call((hub) => hub.GET("/api/v1/admin/llm-usage", { params: { query: { days: 7 } } })),
  });
  const counts = useQuery({
    queryKey: ["admin", "stats"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/admin/stats/assessments")),
  });
  const cost = (usage.data ?? []).reduce((sum, row) => sum + Number(row.cost_usd), 0);
  const statuses = [...new Set((counts.data ?? []).flatMap((row) => Object.keys(row.by_status)))];
  const verdicts = [...new Set((counts.data ?? []).flatMap((row) => Object.keys(row.by_verdict)))];

  return (
    <>
      <PageHeader title="Overview" />
      <div className="grid gap-4 md:grid-cols-3">
        <Figure
          title="Attributes to curate"
          value={proposals.data?.length}
          to="/proposals"
          hint="provisional, shared as information until you decide"
        />
        <Figure
          title="Failed jobs"
          value={failed.data?.length}
          to="/jobs"
          hint="catalog readings and proposals can be retried"
        />
        <Figure
          title="LLM cost, 7 days"
          value={usage.data ? usd(cost) : undefined}
          to="/llm"
          hint="all pipelines, our key"
        />
      </div>
      <Card className="mt-4">
        <CardTitle>Assessments per hospital</CardTitle>
        <p className="mb-3 text-xs text-neutral-500">
          Counts only: an assessment belongs to its hospital.
        </p>
        {counts.isPending ? (
          <Spinner />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Hospital</Th>
                {statuses.map((status) => (
                  <Th key={status}>{status.replaceAll("_", " ").toLowerCase()}</Th>
                ))}
                {verdicts.map((verdict) => (
                  <Th key={verdict}>→ {verdict.replaceAll("_", " ").toLowerCase()}</Th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(counts.data ?? []).map((row) => (
                <tr key={row.tenant_code}>
                  <Td>{row.tenant_code}</Td>
                  {statuses.map((status) => (
                    <Td key={status}>{row.by_status[status] ?? 0}</Td>
                  ))}
                  {verdicts.map((verdict) => (
                    <Td key={verdict}>{row.by_verdict[verdict] ?? 0}</Td>
                  ))}
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}

function Figure({
  title,
  value,
  to,
  hint,
}: {
  title: string;
  value: number | string | undefined;
  to: string;
  hint: string;
}) {
  return (
    <Card>
      <Link to={to} className="block hover:underline">
        <p className="text-sm text-neutral-500">{title}</p>
        <p className="text-2xl font-semibold">{value ?? "…"}</p>
      </Link>
      <p className="mt-1 text-xs text-neutral-500">{hint}</p>
    </Card>
  );
}
