import {
  Badge,
  Card,
  Empty,
  Label,
  Select,
  cn,
  CardTitle,
  CriticalityBadge,
  JudgmentBadge,
  Table,
  Td,
  Th,
  ValueView,
  VerdictBadge,
} from "@sanovio/ui";
import { useState } from "react";

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
  const all = round.attribute_judgments as unknown as JudgmentRow[];
  const [sort, setSort] = useState<SortKey>("criticality");
  const [filter, setFilter] = useState<FilterKey>("all");
  const [byModel, setByModel] = useState(false);
  const rows = arrange(all, sort, filter, byModel, (key) => labelFor(template, key));
  return (
    <Card>
      <CardTitle>Comparison · round {round.round_no}</CardTitle>
      {round.identifier_evidence === "SAME_TRADE_ITEM" ? (
        <p className="text-sm">
          Both sides carry the same valid GTIN: this is the product you already buy. No attribute
          needed comparing.
        </p>
      ) : (
        <>
          <Toolbar
            rows={all}
            sort={sort}
            filter={filter}
            byModel={byModel}
            onSort={setSort}
            onFilter={setFilter}
            onByModel={setByModel}
          />
          {rows.length === 0 && <Empty>Nothing matches this filter.</Empty>}
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
        </>
      )}
    </Card>
  );
}

type SortKey = "criticality" | "judgment" | "attribute";
type FilterKey = "all" | "mismatch" | "deviation" | "gap" | "match" | "info";

/** Filter groups over the judgment statuses (§8.4); a gap is anything still unknown. */
const GROUPS: Record<Exclude<FilterKey, "all">, { label: string; statuses: string[] }> = {
  mismatch: { label: "mismatch", statuses: ["MISMATCH"] },
  deviation: { label: "deviation", statuses: ["ACCEPTABLE_DEVIATION"] },
  gap: { label: "unknown", statuses: ["UNKNOWN", "UNAVAILABLE", "NEEDS_JUDGE"] },
  match: { label: "match", statuses: ["MATCH"] },
  info: { label: "info", statuses: ["INFO"] },
};
const CRITICALITY_ORDER: Record<string, number> = { critical: 0, major: 1, minor: 2 };
// Worst first: what blocks equivalence before what is fine.
const JUDGMENT_ORDER = [
  "MISMATCH",
  "UNKNOWN",
  "UNAVAILABLE",
  "NEEDS_JUDGE",
  "ACCEPTABLE_DEVIATION",
  "MATCH",
  "INFO",
];

function arrange(
  rows: JudgmentRow[],
  sort: SortKey,
  filter: FilterKey,
  byModel: boolean,
  label: (key: string) => string,
): JudgmentRow[] {
  const shown = rows.filter(
    (row) =>
      (filter === "all" || GROUPS[filter].statuses.includes(row.status)) &&
      (!byModel || row.decided_by === "LLM"),
  );
  const rank = {
    criticality: (row: JudgmentRow) => CRITICALITY_ORDER[row.criticality] ?? 9,
    judgment: (row: JudgmentRow) => JUDGMENT_ORDER.indexOf(row.status),
    attribute: () => 0,
  }[sort];
  return [...shown].sort(
    (a, b) => rank(a) - rank(b) || label(a.attribute_key).localeCompare(label(b.attribute_key)),
  );
}

function Toolbar({
  rows,
  sort,
  filter,
  byModel,
  onSort,
  onFilter,
  onByModel,
}: {
  rows: JudgmentRow[];
  sort: SortKey;
  filter: FilterKey;
  byModel: boolean;
  onSort: (sort: SortKey) => void;
  onFilter: (filter: FilterKey) => void;
  onByModel: (byModel: boolean) => void;
}) {
  const count = (key: Exclude<FilterKey, "all">) =>
    rows.filter((row) => GROUPS[key].statuses.includes(row.status)).length;
  const chip = (key: FilterKey, text: string) => (
    <button
      key={key}
      type="button"
      aria-pressed={filter === key}
      onClick={() => {
        onFilter(key);
      }}
      className={cn(
        "rounded-full border px-2.5 py-0.5 text-xs",
        filter === key
          ? "border-accent bg-accent text-accent-foreground"
          : "border-neutral-300 text-neutral-700 hover:bg-neutral-50",
      )}
    >
      {text}
    </button>
  );
  return (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      {chip("all", `all ${rows.length}`)}
      {(Object.keys(GROUPS) as Exclude<FilterKey, "all">[]).map((key) =>
        chip(key, `${GROUPS[key].label} ${count(key)}`),
      )}
      <Label className="ml-2 flex items-center gap-1 text-xs font-normal">
        <input
          type="checkbox"
          checked={byModel}
          onChange={(event) => {
            onByModel(event.target.checked);
          }}
        />
        decided by model
      </Label>
      <div className="ml-auto flex items-center gap-2">
        <Label htmlFor="comparison-sort" className="text-xs">
          Sort by
        </Label>
        <Select
          id="comparison-sort"
          className="h-8 w-36"
          value={sort}
          onChange={(event) => {
            onSort(event.target.value as SortKey);
          }}
        >
          <option value="criticality">criticality</option>
          <option value="judgment">judgment</option>
          <option value="attribute">attribute</option>
        </Select>
      </div>
    </div>
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
