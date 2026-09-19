import type { HubSchemas } from "@sanovio/api";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  Empty,
  ErrorMessage,
  Table,
  Td,
  Th,
  formatValue,
} from "@sanovio/ui";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import { useSession } from "../sessionContext";
import { RequirementPanel } from "../shared/RequirementPanel";
import { issueRequirement, type Requirement } from "../shared/requirements";
import type { Article } from "./queries";
import { CurrentProductDialog } from "./CurrentProductDialog";
import { StartAssessmentDialog } from "./StartAssessmentDialog";

type SearchResponse = HubSchemas["schemas"]["SearchResponse"];
export type Candidate = HubSchemas["schemas"]["CandidateView"];

interface Result {
  requirement: Requirement;
  response: SearchResponse;
}

/** One candidate search at the hub, built from this article's requirement only (§15, D46). */
export function SearchCard({ article }: { article: Article }) {
  const { session } = useSession();
  const [marking, setMarking] = useState<Candidate | null>(null);
  const [starting, setStarting] = useState<Candidate | null>(null);
  const search = useMutation({
    mutationFn: async (): Promise<Result> => {
      const requirement = await issueRequirement(session, article.id);
      const response = await session.atHub((hub) =>
        hub.POST("/api/v1/search", { body: { requirement, limit: 50 } }),
      );
      return { requirement, response };
    },
  });
  const result = search.data;

  return (
    <Card>
      <div className="mb-3 flex items-center justify-between">
        <CardTitle className="mb-0">Candidates</CardTitle>
        <Button
          disabled={search.isPending}
          onClick={() => {
            search.mutate();
          }}
        >
          {search.isPending ? "Searching…" : result ? "Search again" : "Search the hub"}
        </Button>
      </div>
      <ErrorMessage error={search.error} />
      {result && (
        <div className="space-y-3">
          <RequirementPanel requirement={result.requirement} />
          <SearchSummary response={result.response} />
          {result.response.candidates.length === 0 ? (
            <Empty>No candidate passes the hard filters.</Empty>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Candidate</Th>
                  <Th>Score</Th>
                  <Th>Coverage</Th>
                  <Th>Critical unknowns</Th>
                  <Th>Pre-check</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {result.response.candidates.map((candidate) => (
                  <CandidateRow
                    key={candidate.variant_id}
                    candidate={candidate}
                    onMark={() => {
                      setMarking(candidate);
                    }}
                    onStart={() => {
                      setStarting(candidate);
                    }}
                  />
                ))}
              </tbody>
            </Table>
          )}
        </div>
      )}
      {marking && (
        <CurrentProductDialog
          article={article}
          candidate={marking}
          onClose={(changed) => {
            setMarking(null);
            // The article now knows more: search again on the extended parameter set (§15).
            if (changed) search.mutate();
          }}
        />
      )}
      {starting && (
        <StartAssessmentDialog
          article={article}
          candidate={starting}
          onClose={() => {
            setStarting(null);
          }}
        />
      )}
    </Card>
  );
}

function SearchSummary({ response }: { response: SearchResponse }) {
  const filters = Object.entries(response.search_spec.hard_filters);
  const excluded = Object.entries(response.excluded_by);
  return (
    <div className="grid gap-2 text-xs text-neutral-600 sm:grid-cols-3">
      <div>
        <div className="font-semibold text-neutral-700">Hard filters</div>
        {filters.length
          ? filters.map(([key, value]) => (
              <div key={key}>
                {key}: {formatValue(value)}
              </div>
            ))
          : "none"}
      </div>
      <div>
        <div className="font-semibold text-neutral-700">Excluded by</div>
        {excluded.length
          ? excluded.map(([key, count]) => (
              <div key={key}>
                {key}: {count}
              </div>
            ))
          : "nothing"}
      </div>
      <div>
        <div className="font-semibold text-neutral-700">Unknown at the hospital</div>
        {response.hospital_gaps.length ? response.hospital_gaps.join(", ") : "nothing"}
      </div>
    </div>
  );
}

function CandidateRow({
  candidate,
  onMark,
  onStart,
}: {
  candidate: Candidate;
  onMark: () => void;
  onStart: () => void;
}) {
  const counts = new Map<string, number>();
  for (const entry of candidate.precheck) {
    counts.set(entry.status, (counts.get(entry.status) ?? 0) + 1);
  }
  return (
    <tr>
      <Td>
        <div className="font-medium">{candidate.display_name}</div>
        <div className="text-xs text-neutral-500">
          {candidate.supplier} · {candidate.family}
        </div>
        {candidate.identifier_match && (
          <Badge tone="good">{`same ${candidate.identifier_match}`}</Badge>
        )}
      </Td>
      <Td>{candidate.score.toFixed(2)}</Td>
      <Td>{Math.round(candidate.coverage * 100)}%</Td>
      <Td>{candidate.critical_unknowns}</Td>
      <Td className="space-x-1 text-xs">
        {[...counts].map(([status, count]) => (
          <span key={status} className="whitespace-nowrap">
            {count} {status.toLowerCase()}
          </span>
        ))}
      </Td>
      <Td className="space-y-1 text-right">
        <Button size="sm" variant="secondary" onClick={onMark}>
          This is our current product
        </Button>
        <Button size="sm" onClick={onStart}>
          Start assessment
        </Button>
      </Td>
    </tr>
  );
}
