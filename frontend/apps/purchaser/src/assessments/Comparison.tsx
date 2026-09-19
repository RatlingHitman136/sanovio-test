import {
  Badge,
  Card,
  CardTitle,
  CriticalityBadge,
  JudgmentBadge,
  Table,
  Td,
  Th,
  ValueView,
  VerdictBadge,
} from "@sanovio/ui";

import type { Article } from "../articles/queries";
import { labelFor, type TemplateDefinition } from "../shared/templates";
import type { Round } from "./queries";

interface Side {
  value?: unknown;
  origin?: string;
  scope?: string | null;
}

interface JudgmentRow {
  attribute_key: string;
  criticality: string;
  status: string;
  decided_by?: string;
  hospital?: Side | null;
  supplier?: Side | null;
  detail?: string | null;
  rationale?: string | null;
}

/** Attribute by attribute (§8): the hospital's side with its source, joined from the node. */
export function ComparisonCard({
  round,
  article,
  template,
}: {
  round: Round;
  article: Article | undefined;
  template: TemplateDefinition | undefined;
}) {
  const sources = new Map(article?.attributes.map((fact) => [fact.key, fact.source]));
  const rows = round.attribute_judgments as unknown as JudgmentRow[];
  return (
    <Card>
      <CardTitle>Comparison · round {round.round_no}</CardTitle>
      {round.identifier_evidence === "SAME_TRADE_ITEM" ? (
        <p className="text-sm">
          Both sides carry the same valid GTIN: this is the product you already buy. No attribute
          needed comparing.
        </p>
      ) : (
        <Table>
          <thead>
            <tr>
              <Th>Attribute</Th>
              <Th>Ours</Th>
              <Th>Candidate</Th>
              <Th>Judgment</Th>
              <Th>Weight</Th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.attribute_key}>
                <Td>{labelFor(template, row.attribute_key)}</Td>
                <Td>
                  <ValueView value={row.hospital?.value} />
                  {row.hospital && (
                    <div className="text-xs text-neutral-500">
                      {sources.get(row.attribute_key) ?? row.hospital.origin}
                    </div>
                  )}
                </Td>
                <Td>
                  <ValueView value={row.supplier?.value} />
                  {row.supplier?.scope && (
                    <div className="text-xs text-neutral-500">
                      {row.supplier.scope.toLowerCase()}
                    </div>
                  )}
                </Td>
                <Td>
                  <JudgmentBadge status={row.status} />
                  {row.decided_by === "LLM" && <Badge tone="info">judge</Badge>}
                  {(row.rationale ?? row.detail) && (
                    <div className="mt-1 text-xs text-neutral-500">
                      {row.rationale ?? row.detail}
                    </div>
                  )}
                </Td>
                <Td>
                  <CriticalityBadge criticality={row.criticality} />
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </Card>
  );
}

export function VerdictCard({ round }: { round: Round }) {
  return (
    <Card>
      <CardTitle>Verdict · round {round.round_no}</CardTitle>
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-neutral-500">Rules</dt>
        <dd>
          <VerdictBadge verdict={round.rule_verdict} />
        </dd>
        <dt className="text-neutral-500">Judge</dt>
        <dd>
          <VerdictBadge verdict={round.llm_verdict} />
          {round.disagreement && (
            <span className="ml-2">
              <Badge tone="warn">disagrees with the rules</Badge>
            </span>
          )}
        </dd>
      </dl>
      {round.rationale && <p className="mt-3 text-sm text-neutral-700">{round.rationale}</p>}
      <p className="mt-2 text-xs text-neutral-500">
        The rules decide; the judge&apos;s verdict is a cross-check.
      </p>
    </Card>
  );
}
