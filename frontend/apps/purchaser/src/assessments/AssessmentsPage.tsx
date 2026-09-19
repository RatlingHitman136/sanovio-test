import {
  Card,
  Empty,
  Label,
  PageHeader,
  Select,
  Spinner,
  StatusBadge,
  Table,
  Td,
  Th,
  VerdictBadge,
} from "@sanovio/ui";
import { useState } from "react";
import { Link } from "react-router";

import { useLocalNames } from "../shared/names";
import { useAssessments } from "./queries";

const STATUSES = [
  "NEEDS_QUESTION_REVIEW",
  "PROPOSED_RESOLUTION",
  "NEEDS_MANUAL_DECISION",
  "ASSESSING",
  "AWAITING_ANSWERS",
  "FAILED",
  "RESOLVED",
  "CANCELLED",
];

/** Every assessment of this hospital, with names joined in the browser (§14). */
export function AssessmentsPage() {
  const [status, setStatus] = useState("");
  const [mine, setMine] = useState(false);
  const assessments = useAssessments({ status, mine });
  const names = useLocalNames((assessments.data ?? []).map((row) => row.article_ref));

  return (
    <>
      <PageHeader title="Assessments">
        <Select
          aria-label="Status"
          className="w-56"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
          }}
        >
          <option value="">All statuses</option>
          {STATUSES.map((code) => (
            <option key={code} value={code}>
              {code.replaceAll("_", " ").toLowerCase()}
            </option>
          ))}
        </Select>
        <Label className="flex items-center gap-2 font-normal">
          <input
            type="checkbox"
            checked={mine}
            onChange={(event) => {
              setMine(event.target.checked);
            }}
          />
          Assigned to me
        </Label>
      </PageHeader>
      <Card>
        {assessments.isPending ? (
          <Spinner />
        ) : !assessments.data?.length ? (
          <Empty>No assessments yet. Start one from an article&apos;s search results.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Our article</Th>
                <Th>Candidate</Th>
                <Th>Status</Th>
                <Th>Round</Th>
                <Th>Verdict</Th>
                <Th>Assigned to</Th>
              </tr>
            </thead>
            <tbody>
              {assessments.data.map((row) => (
                <tr key={row.id}>
                  <Td>{names.article(row.article_ref)?.name ?? row.article_ref}</Td>
                  <Td>
                    <Link to={`/assessments/${row.id}`} className="text-accent hover:underline">
                      {row.variant_label}
                    </Link>
                    <div className="text-xs text-neutral-500">{row.supplier}</div>
                  </Td>
                  <Td>
                    <StatusBadge status={row.status} />
                  </Td>
                  <Td>{row.current_round}</Td>
                  <Td>
                    <VerdictBadge verdict={row.final_verdict ?? row.proposed_verdict} />
                  </Td>
                  <Td>{names.person(row.assigned_to_subject_id)}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
