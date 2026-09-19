import type { HubSchemas } from "@sanovio/api";
import {
  Badge,
  Button,
  Card,
  Dialog,
  Empty,
  ErrorMessage,
  Input,
  Label,
  Notice,
  PageHeader,
  Select,
  Spinner,
  Table,
  Td,
  Textarea,
  Th,
  cn,
} from "@sanovio/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useSession } from "../sessionContext";
import { Field } from "./Field";
import { CRITICALITIES, RULES, type Criticality, type Rule } from "./shared";

type Proposal = HubSchemas["schemas"]["AttributeProposalView"];
type Status = HubSchemas["schemas"]["ProposalStatus"];

/** What the proposal job suggested for a new attribute (H.22 `proposal`). */
interface Suggested {
  key: string;
  type: string;
  unit: string | null;
  options: string[];
  labels: { de: string; en: string };
  rationale?: string;
}

const TABS: Status[] = [
  "PROVISIONAL",
  "PENDING",
  "APPROVED",
  "MERGED",
  "REJECTED",
  "MATCHED",
  "ROUTED",
];

type Action = "approve" | "merge" | "reject";

const TITLE: Record<Action, string> = { approve: "Approve", merge: "Merge", reject: "Reject" };

/** New attributes from free questions: only an operator decides whether and how they count
 * (§7.2 step 6). Until then they are shared as information and never judged. */
export function ProposalsPage() {
  const { session } = useSession();
  const [status, setStatus] = useState<Status>("PROVISIONAL");
  const [acting, setActing] = useState<{ proposal: Proposal; action: Action } | null>(null);
  const proposals = useQuery({
    queryKey: ["admin", "proposals", status],
    queryFn: () =>
      session.call((hub) =>
        hub.GET("/api/v1/admin/attribute-proposals", { params: { query: { status } } }),
      ),
  });

  return (
    <>
      <PageHeader title="Curation" />
      <div className="mb-4 flex flex-wrap gap-2" role="tablist">
        {TABS.map((tab) => (
          <button
            key={tab}
            role="tab"
            aria-selected={tab === status}
            className={cn(
              "rounded-full border px-3 py-1 text-sm",
              tab === status ? "border-accent bg-accent text-accent-foreground" : "bg-white",
            )}
            onClick={() => {
              setStatus(tab);
            }}
          >
            {tab.toLowerCase()}
          </button>
        ))}
      </div>
      <Card>
        {proposals.isPending ? (
          <Spinner />
        ) : !proposals.data?.length ? (
          <Empty>No proposals here.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Question</Th>
                <Th>Category</Th>
                <Th>Attribute</Th>
                <Th>Values shared</Th>
                <Th>Note</Th>
                <Th />
              </tr>
            </thead>
            <tbody>
              {proposals.data.map((proposal) => {
                const suggested = proposal.proposal as Suggested | null;
                return (
                  <tr key={proposal.id}>
                    <Td className="max-w-sm">{proposal.question_text}</Td>
                    <Td className="text-xs">{proposal.category_code}</Td>
                    <Td>
                      {proposal.attribute_key ?? proposal.identifier_key ?? "–"}
                      {suggested && (
                        <p className="text-xs text-neutral-500">
                          {suggested.type}
                          {suggested.unit ? ` (${suggested.unit})` : ""} · {suggested.labels.en}
                        </p>
                      )}
                    </Td>
                    <Td>{proposal.value_count}</Td>
                    <Td className="text-xs text-neutral-600">
                      {proposal.review_note ?? suggested?.rationale ?? ""}
                    </Td>
                    <Td className="space-x-1 whitespace-nowrap text-right">
                      {proposal.status === "PROVISIONAL" &&
                        (["approve", "merge", "reject"] as const).map((action) => (
                          <Button
                            key={action}
                            size="sm"
                            variant={action === "approve" ? "primary" : "secondary"}
                            onClick={() => {
                              setActing({ proposal, action });
                            }}
                          >
                            {TITLE[action]}
                          </Button>
                        ))}
                      {proposal.status !== "PROVISIONAL" && (
                        <Badge>{proposal.status.toLowerCase()}</Badge>
                      )}
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>
      {acting && (
        <DecisionDialog
          {...acting}
          onClose={() => {
            setActing(null);
          }}
        />
      )}
    </>
  );
}

function DecisionDialog({
  proposal,
  action,
  onClose,
}: {
  proposal: Proposal;
  action: Action;
  onClose: () => void;
}) {
  const { session } = useSession();
  const queries = useQueryClient();
  const suggested = proposal.proposal as Suggested | null;
  const [criticality, setCriticality] = useState<Criticality>("major");
  const [rule, setRule] = useState<Rule>("exact");
  const [tolerance, setTolerance] = useState("");
  const [shareable, setShareable] = useState(true);
  const [labels, setLabels] = useState(suggested?.labels ?? { de: "", en: "" });
  const [target, setTarget] = useState("");
  const [note, setNote] = useState("");
  const path = { params: { path: { proposal_id: proposal.id } } };

  const decide = useMutation({
    mutationFn: () =>
      session.call((hub) => {
        if (action === "approve") {
          return hub.POST("/api/v1/admin/attribute-proposals/{proposal_id}/approve", {
            ...path,
            body: {
              criticality,
              rule,
              tolerance: rule === "tolerance" ? Number(tolerance) : null,
              shareable,
              labels,
            },
          });
        }
        if (action === "merge") {
          return hub.POST("/api/v1/admin/attribute-proposals/{proposal_id}/merge", {
            ...path,
            body: { attribute_key: target, note },
          });
        }
        return hub.POST("/api/v1/admin/attribute-proposals/{proposal_id}/reject", {
          ...path,
          body: { note },
        });
      }),
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
  });
  const ready =
    action === "approve"
      ? labels.de.trim() !== "" &&
        labels.en.trim() !== "" &&
        (rule !== "tolerance" || tolerance !== "")
      : note.trim() !== "" && (action === "reject" || target !== "");

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={`${TITLE[action]}: ${proposal.attribute_key ?? ""}`}
      footer={
        <Button
          variant={action === "reject" ? "danger" : "primary"}
          disabled={!ready || decide.isPending}
          onClick={() => {
            decide.mutate();
          }}
        >
          {TITLE[action]}
        </Button>
      }
    >
      <div className="space-y-3">
        <p className="text-sm text-neutral-600">“{proposal.question_text}”</p>
        {action === "approve" && (
          <>
            <Notice>
              The attribute joins {proposal.category_code}. Nodes pick the new definition up at
              their next sync.
            </Notice>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Criticality" id="criticality">
                <Select
                  id="criticality"
                  value={criticality}
                  onChange={(event) => {
                    setCriticality(event.target.value as Criticality);
                  }}
                >
                  {CRITICALITIES.map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </Select>
              </Field>
              <Field label="Rule" id="rule">
                <Select
                  id="rule"
                  value={rule}
                  onChange={(event) => {
                    setRule(event.target.value as Rule);
                  }}
                >
                  {RULES.map((value) => (
                    <option key={value}>{value}</option>
                  ))}
                </Select>
              </Field>
              {rule === "tolerance" && (
                <Field label="Tolerance" id="tolerance">
                  <Input
                    id="tolerance"
                    inputMode="decimal"
                    value={tolerance}
                    onChange={(event) => {
                      setTolerance(event.target.value);
                    }}
                  />
                </Field>
              )}
              <Field label="Label (de)" id="label-de">
                <Input
                  id="label-de"
                  value={labels.de}
                  onChange={(event) => {
                    setLabels({ ...labels, de: event.target.value });
                  }}
                />
              </Field>
              <Field label="Label (en)" id="label-en">
                <Input
                  id="label-en"
                  value={labels.en}
                  onChange={(event) => {
                    setLabels({ ...labels, en: event.target.value });
                  }}
                />
              </Field>
            </div>
            <Label className="flex items-center gap-2 font-normal">
              <input
                type="checkbox"
                checked={shareable}
                onChange={(event) => {
                  setShareable(event.target.checked);
                }}
              />
              Shareable: may leave the hospital in a requirement
            </Label>
          </>
        )}
        {action === "merge" && suggested && (
          <MergeTarget suggested={suggested} value={target} onChange={setTarget} />
        )}
        {action !== "approve" && (
          <Field label="Note" id="note">
            <Textarea
              id="note"
              value={note}
              onChange={(event) => {
                setNote(event.target.value);
              }}
            />
          </Field>
        )}
        {action === "reject" && (
          <p className="text-xs text-neutral-500">
            The attribute is deprecated: its values are kept for audit and no longer shown.
          </p>
        )}
        <ErrorMessage error={decide.error} />
      </div>
    </Dialog>
  );
}

/** Only approved attributes of the same type (and unit) can take the values over. */
function MergeTarget({
  suggested,
  value,
  onChange,
}: {
  suggested: Suggested;
  value: string;
  onChange: (key: string) => void;
}) {
  const { session } = useSession();
  const attributes = useQuery({
    queryKey: ["admin", "attributes", "APPROVED"],
    queryFn: () =>
      session.call((hub) =>
        hub.GET("/api/v1/attributes", { params: { query: { status: "APPROVED" } } }),
      ),
  });
  const fitting = (attributes.data ?? []).filter(
    (attribute) =>
      attribute.kind === "ATTRIBUTE" &&
      attribute.value_type === suggested.type &&
      (attribute.unit ?? null) === (suggested.unit ?? null),
  );
  return (
    <Field label="Merge into" id="target">
      <Select
        id="target"
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        <option value="">Choose an attribute…</option>
        {fitting.map((attribute) => (
          <option key={attribute.key} value={attribute.key}>
            {attribute.key} · {(attribute.labels as { en?: string }).en}
          </option>
        ))}
      </Select>
    </Field>
  );
}
