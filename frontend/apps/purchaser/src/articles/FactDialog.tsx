import type { NodeSchemas } from "@sanovio/api";
import { Button, Dialog, ErrorMessage, Label, ValueInput, type TypedValue } from "@sanovio/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { useSession } from "../sessionContext";
import { expectedFor, labelFor, useTemplates } from "../shared/templates";
import type { Article } from "./queries";

type FactValue = NonNullable<NodeSchemas["schemas"]["FactUpdate"]["value"]>;

/** The purchaser's own value for one attribute; it outranks every other source (§9). */
export function FactDialog({
  article,
  attributeKey,
  onClose,
}: {
  article: Article;
  attributeKey: string;
  onClose: () => void;
}) {
  const { session } = useSession();
  const queries = useQueryClient();
  const templates = useTemplates();
  const template = templates.data?.get(article.category_code ?? "");
  const [value, setValue] = useState<TypedValue | null>(null);
  const [cannotProvide, setCannotProvide] = useState(false);
  const save = useMutation({
    mutationFn: () =>
      session.atNode((node) =>
        node.PUT("/api/v1/articles/{article_id}/facts/{attribute_key}", {
          params: { path: { article_id: article.id, attribute_key: attributeKey } },
          body: {
            cannot_provide: cannotProvide,
            value: cannotProvide ? null : (value as FactValue),
          },
        }),
      ),
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: ["node"] });
      onClose();
    },
  });
  const label = labelFor(template, attributeKey);
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={label}
      footer={
        <Button
          disabled={save.isPending || (!cannotProvide && value === null)}
          onClick={() => {
            save.mutate();
          }}
        >
          Save
        </Button>
      }
    >
      <div className="space-y-3">
        <ValueInput
          label={label}
          expected={expectedFor(template, attributeKey)}
          value={value}
          onChange={setValue}
          disabled={cannotProvide}
        />
        <Label className="flex items-center gap-2 font-normal">
          <input
            type="checkbox"
            checked={cannotProvide}
            onChange={(event) => {
              setCannotProvide(event.target.checked);
            }}
          />
          We cannot provide this
        </Label>
        <ErrorMessage error={save.error} />
      </div>
    </Dialog>
  );
}
