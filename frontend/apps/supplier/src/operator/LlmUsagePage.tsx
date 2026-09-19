import { Card, CardTitle, Empty, PageHeader, Select, Spinner, Table, Td, Th } from "@sanovio/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { useSession } from "../sessionContext";
import { usd, when } from "./shared";

interface Totals {
  purpose: string;
  model: string;
  calls: number;
  errors: number;
  input: number;
  output: number;
  cost: number;
  p95: number;
}

/** What the pipelines cost on our key. Prompts and answers are never shown: they hold
 * hospital values (D58). */
export function LlmUsagePage() {
  const { session } = useSession();
  const [days, setDays] = useState(7);
  const usage = useQuery({
    queryKey: ["admin", "llm-usage", days],
    queryFn: () =>
      session.call((hub) => hub.GET("/api/v1/admin/llm-usage", { params: { query: { days } } })),
  });
  const failures = useQuery({
    queryKey: ["admin", "llm-failures"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/admin/llm-usage/failures")),
  });

  const rows = usage.data ?? [];
  const totals = new Map<string, Totals>();
  for (const row of rows) {
    const key = `${row.purpose} ${row.model}`;
    const sum = totals.get(key) ?? {
      purpose: row.purpose,
      model: row.model,
      calls: 0,
      errors: 0,
      input: 0,
      output: 0,
      cost: 0,
      p95: 0,
    };
    sum.calls += row.calls;
    sum.errors += row.errors;
    sum.input += row.input_tokens;
    sum.output += row.output_tokens;
    sum.cost += Number(row.cost_usd);
    sum.p95 = Math.max(sum.p95, row.p95_latency_ms);
    totals.set(key, sum);
  }
  const daily = new Map<string, number>();
  for (const row of rows) daily.set(row.day, (daily.get(row.day) ?? 0) + Number(row.cost_usd));
  const highest = Math.max(...daily.values(), 0);

  return (
    <>
      <PageHeader title="LLM usage">
        <Select
          aria-label="Period"
          value={days}
          onChange={(event) => {
            setDays(Number(event.target.value));
          }}
        >
          <option value={1}>last day</option>
          <option value={7}>last 7 days</option>
          <option value={30}>last 30 days</option>
        </Select>
      </PageHeader>
      <div className="space-y-4">
        <Card>
          <CardTitle>Per pipeline and model</CardTitle>
          {usage.isPending ? (
            <Spinner />
          ) : !totals.size ? (
            <Empty>No calls in this period.</Empty>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Pipeline</Th>
                  <Th>Model</Th>
                  <Th>Calls</Th>
                  <Th>Errors</Th>
                  <Th>Tokens in / out</Th>
                  <Th>p95 latency (worst day)</Th>
                  <Th>Cost</Th>
                </tr>
              </thead>
              <tbody>
                {[...totals.values()].map((sum) => (
                  <tr key={`${sum.purpose} ${sum.model}`}>
                    <Td className="text-xs">{sum.purpose.toLowerCase()}</Td>
                    <Td className="text-xs">{sum.model}</Td>
                    <Td>{sum.calls}</Td>
                    <Td>{sum.errors}</Td>
                    <Td className="text-xs">
                      {sum.input} / {sum.output}
                    </Td>
                    <Td className="text-xs">{(sum.p95 / 1000).toFixed(1)} s</Td>
                    <Td>{usd(sum.cost)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
        <Card>
          <CardTitle>Cost per day</CardTitle>
          <ul className="space-y-1">
            {[...daily.entries()].map(([day, cost]) => (
              <li key={day} className="flex items-center gap-3 text-xs">
                <span className="w-24">{day}</span>
                <span
                  className="h-3 rounded bg-accent"
                  style={{ width: `${highest ? (cost / highest) * 60 : 0}%` }}
                />
                <span>{usd(cost)}</span>
              </li>
            ))}
          </ul>
        </Card>
        <Card>
          <CardTitle>Recent failed calls</CardTitle>
          {!failures.data?.length ? (
            <Empty>None.</Empty>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>When</Th>
                  <Th>Pipeline</Th>
                  <Th>Model</Th>
                  <Th>Failure</Th>
                </tr>
              </thead>
              <tbody>
                {failures.data.map((failure) => (
                  <tr key={failure.id}>
                    <Td className="text-xs">{when(failure.created_at)}</Td>
                    <Td className="text-xs">{failure.purpose.toLowerCase()}</Td>
                    <Td className="text-xs">{failure.model}</Td>
                    <Td className="text-xs text-red-700">{failure.error_kind}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
    </>
  );
}
