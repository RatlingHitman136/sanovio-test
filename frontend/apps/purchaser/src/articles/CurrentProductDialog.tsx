import type { NodeSchemas } from "@sanovio/api";
import {
  Button,
  Dialog,
  ErrorMessage,
  Select,
  Spinner,
  Table,
  Td,
  Th,
  ValueView,
} from "@sanovio/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useSession } from "../sessionContext";
import type { Article } from "./queries";
import type { Candidate } from "./SearchCard";

type Choice = NodeSchemas["schemas"]["Choice"];
type ReferenceInput = NodeSchemas["schemas"]["ReferenceInput"];

/**
 * "This is our current product" (§8.2): the hub variant's values are copied into the node,
 * after a preview. Conflicts with the hospital's own values need an explicit choice.
 */
export function CurrentProductDialog({
  article,
  candidate,
  onClose,
}: {
  article: Article;
  candidate: Candidate;
  onClose: (changed: boolean) => void;
}) {
  const { session } = useSession();
  const queries = useQueryClient();
  const [choices, setChoices] = useState<Record<string, Choice>>({});

  const preview = useQuery({
    queryKey: ["reference-preview", article.id, candidate.variant_id],
    queryFn: async () => {
      const variant = await session.atHub((hub) =>
        hub.GET("/api/v1/catalog/variants/{variant_id}/attributes", {
          params: { path: { variant_id: candidate.variant_id } },
        }),
      );
      const reference = {
        variant_id: variant.variant_id,
        label: variant.label,
        attributes: variant.attributes,
      } as unknown as ReferenceInput;
      const plan = await session.atNode((node) =>
        node.POST("/api/v1/articles/{article_id}/reference/preview", {
          params: { path: { article_id: article.id } },
          body: reference,
        }),
      );
      return { reference, plan };
    },
  });

  const link = useMutation({
    mutationFn: () =>
      session.atNode((node) =>
        node.PUT("/api/v1/articles/{article_id}/reference", {
          params: { path: { article_id: article.id } },
          body: { ...(preview.data?.reference as ReferenceInput), conflict_choices: choices },
        }),
      ),
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: ["node"] });
      onClose(true);
    },
  });

  const conflicts = preview.data?.plan.conflicts ?? [];
  const undecided = conflicts.some((conflict) => !(conflict.key in choices));
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose(false);
      }}
      title={`Current product: ${candidate.display_name}`}
      footer={
        <Button
          disabled={!preview.data || undecided || link.isPending}
          onClick={() => {
            link.mutate();
          }}
        >
          Mark and search again
        </Button>
      }
    >
      {preview.isPending ? (
        <Spinner />
      ) : !preview.data ? (
        <ErrorMessage error={preview.error} />
      ) : (
        <div className="space-y-4 text-sm">
          <section>
            <h3 className="mb-1 font-medium">Filled in ({preview.data.plan.fills.length})</h3>
            {preview.data.plan.fills.length === 0 ? (
              <p className="text-neutral-500">Nothing new.</p>
            ) : (
              <ul className="grid grid-cols-2 gap-x-4">
                {preview.data.plan.fills.map((fill) => (
                  <li key={fill.key}>
                    {fill.key}: <ValueView value={fill.value} />
                  </li>
                ))}
              </ul>
            )}
          </section>
          {conflicts.length > 0 && (
            <section>
              <h3 className="mb-1 font-medium">Conflicts: choose which value holds</h3>
              <Table>
                <thead>
                  <tr>
                    <Th>Attribute</Th>
                    <Th>Ours</Th>
                    <Th>Current product</Th>
                    <Th>Keep</Th>
                  </tr>
                </thead>
                <tbody>
                  {conflicts.map((conflict) => (
                    <tr key={conflict.key}>
                      <Td>{conflict.key}</Td>
                      <Td>
                        <ValueView value={conflict.ours} />
                        <div className="text-xs text-neutral-500">{conflict.ours_source}</div>
                      </Td>
                      <Td>
                        <ValueView value={conflict.theirs} />
                      </Td>
                      <Td>
                        <Select
                          aria-label={`Choice for ${conflict.key}`}
                          value={choices[conflict.key] ?? ""}
                          onChange={(event) => {
                            setChoices({
                              ...choices,
                              [conflict.key]: event.target.value as Choice,
                            });
                          }}
                        >
                          <option value="">choose…</option>
                          <option value="KEEP_OURS">ours</option>
                          <option value="TAKE_REFERENCE">current product</option>
                        </Select>
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </section>
          )}
          <ErrorMessage error={link.error} />
        </div>
      )}
    </Dialog>
  );
}
