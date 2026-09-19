import type { HubSchemas } from "@sanovio/api";
import {
  Badge,
  Button,
  Card,
  Empty,
  ErrorMessage,
  PageHeader,
  Select,
  Spinner,
  Table,
  Td,
  Th,
} from "@sanovio/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useSession } from "../sessionContext";
import { when } from "./shared";

type JobStatus = HubSchemas["schemas"]["JobStatus"];
type JobKind = HubSchemas["schemas"]["JobKind"];

const STATUSES: JobStatus[] = ["FAILED", "QUEUED", "RUNNING", "SUCCEEDED"];
const KINDS: JobKind[] = [
  "NORMALIZE_ITEM",
  "ASSESS",
  "EXTRACT_ANSWERS",
  "PROPOSE_ATTRIBUTE",
  "REBUILD_PROJECTION",
];
const TONE = { FAILED: "bad", QUEUED: "info", RUNNING: "info", SUCCEEDED: "good" } as const;

/** The hub's queue. A job that moves an assessment is retried by its hospital, never here. */
export function JobsPage() {
  const { session } = useSession();
  const queries = useQueryClient();
  const [status, setStatus] = useState<JobStatus | "">("FAILED");
  const [kind, setKind] = useState<JobKind | "">("");
  const jobs = useQuery({
    queryKey: ["admin", "jobs", status, kind],
    queryFn: () =>
      session.call((hub) =>
        hub.GET("/api/v1/admin/jobs", {
          params: { query: { ...(status && { status }), ...(kind && { kind }) } },
        }),
      ),
  });
  const retry = useMutation({
    mutationFn: (jobId: string) =>
      session.call((hub) =>
        hub.POST("/api/v1/admin/jobs/{job_id}/retry", { params: { path: { job_id: jobId } } }),
      ),
    onSuccess: () => queries.invalidateQueries({ queryKey: ["admin", "jobs"] }),
  });

  return (
    <>
      <PageHeader title="Jobs">
        <Select
          aria-label="Status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as JobStatus | "");
          }}
        >
          <option value="">every status</option>
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {value.toLowerCase()}
            </option>
          ))}
        </Select>
        <Select
          aria-label="Kind"
          value={kind}
          onChange={(event) => {
            setKind(event.target.value as JobKind | "");
          }}
        >
          <option value="">every kind</option>
          {KINDS.map((value) => (
            <option key={value} value={value}>
              {value.toLowerCase()}
            </option>
          ))}
        </Select>
      </PageHeader>
      <Card>
        {jobs.isPending ? (
          <Spinner />
        ) : !jobs.data?.length ? (
          <Empty>No jobs.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Kind</Th>
                <Th>Status</Th>
                <Th>Attempts</Th>
                <Th>Run after</Th>
                <Th>Error</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {jobs.data.map((job) => (
                <tr key={job.id}>
                  <Td className="text-xs">{job.kind.toLowerCase()}</Td>
                  <Td>
                    <Badge tone={TONE[job.status as JobStatus]}>{job.status.toLowerCase()}</Badge>
                  </Td>
                  <Td>
                    {job.attempts}/{job.max_attempts}
                  </Td>
                  <Td className="text-xs">{when(job.run_after)}</Td>
                  <Td className="text-xs text-red-700">{job.last_error ?? ""}</Td>
                  <Td className="text-right text-xs text-neutral-500">
                    {job.retryable ? (
                      <Button
                        size="sm"
                        variant="secondary"
                        disabled={retry.isPending}
                        onClick={() => {
                          retry.mutate(job.id);
                        }}
                      >
                        Retry
                      </Button>
                    ) : (
                      job.status === "FAILED" && "retried by the hospital from its assessment"
                    )}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        <ErrorMessage error={retry.error} />
      </Card>
    </>
  );
}
