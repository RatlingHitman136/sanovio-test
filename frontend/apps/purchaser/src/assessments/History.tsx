import { Card, CardTitle, StatusBadge, VerdictBadge } from "@sanovio/ui";

import type { AssessmentDetail } from "./queries";

export function HistoryCard({ assessment }: { assessment: AssessmentDetail }) {
  return (
    <Card>
      <CardTitle>History</CardTitle>
      <ul className="space-y-1 text-sm">
        {assessment.rounds.map((round) => (
          <li key={round.round_no} className="flex items-center gap-2">
            <span className="text-neutral-500">Round {round.round_no}</span>
            <VerdictBadge verdict={round.rule_verdict} />
            <span className="text-neutral-400">→</span>
            <StatusBadge status={round.outcome_status} />
          </li>
        ))}
      </ul>
      <details className="mt-3">
        <summary className="cursor-pointer text-sm text-neutral-600">
          Timeline ({assessment.events.length} events)
        </summary>
        <ol className="mt-2 space-y-1 text-xs text-neutral-600">
          {assessment.events.map((event, index) => (
            <li key={index}>
              <span className="text-neutral-400">
                {new Date(event.created_at).toLocaleString()}
              </span>{" "}
              {event.type.replaceAll("_", " ").toLowerCase()}
              {event.to_status && ` → ${event.to_status.replaceAll("_", " ").toLowerCase()}`}
            </li>
          ))}
        </ol>
      </details>
    </Card>
  );
}
