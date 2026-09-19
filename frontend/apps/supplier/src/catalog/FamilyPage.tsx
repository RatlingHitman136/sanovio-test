import type { HubSchemas } from "@sanovio/api";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  CriticalityBadge,
  Empty,
  Dialog,
  ErrorMessage,
  Label,
  Notice,
  PageHeader,
  Select,
  Spinner,
  Table,
  Td,
  Th,
  ValueInput,
  ValueView,
  type TypedValue,
} from "@sanovio/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";

import { useSession } from "../sessionContext";
import { FamilyDialog, VariantDialog } from "./FamilyForms";
import { useFamilySaved } from "./useFamilySaved";

type Family = HubSchemas["schemas"]["SupplierFamilyDetail"];
type Attribute = HubSchemas["schemas"]["CatalogAttribute"];
type Value = HubSchemas["schemas"]["CatalogValue"];
type OwnFact = HubSchemas["schemas"]["OwnFact"];

const SOURCE: Record<string, string> = {
  CATALOG: "catalog",
  EXTRACTION: "read from the catalog text",
  SUPPLIER_ANSWER: "set by us",
  UNAVAILABLE: "not available",
};

/** Where an edit goes: the whole family, or one variant as an override. */
interface Target {
  attribute: Attribute;
  familyId?: string;
  variantId?: string;
  label: string;
}

export function FamilyPage() {
  const { familyId = "" } = useParams();
  const { session } = useSession();
  const family = useQuery({
    queryKey: ["family", familyId],
    queryFn: () =>
      session.call((hub) =>
        hub.GET("/api/v1/supplier/catalog/families/{family_id}", {
          params: { path: { family_id: familyId } },
        }),
      ),
    // While the text is being read in the background, look again until it is done.
    refetchInterval: (query) => (query.state.data?.reading ? 3_000 : false),
  });
  const [editingFamily, setEditingFamily] = useState(false);
  const saved = useFamilySaved(() => {
    setEditingFamily(false);
  });

  if (family.isPending) return <Spinner />;
  if (!family.data) return <ErrorMessage error={family.error} />;
  return (
    <>
      <PageHeader title={family.data.name}>
        <Button
          variant="secondary"
          onClick={() => {
            setEditingFamily(true);
          }}
        >
          Edit family
        </Button>
      </PageHeader>
      {editingFamily && (
        <FamilyDialog
          family={family.data}
          manufacturer={family.data.manufacturer}
          onSaved={saved}
          onClose={() => {
            setEditingFamily(false);
          }}
        />
      )}
      <Notice>
        Values you set here outrank the catalog. Open assessments use them in their next round.
      </Notice>
      <FamilyValues detail={family.data} />
    </>
  );
}

/** The family's values and one variant's; `readOnly` for the operator, who never edits them. */
export function FamilyValues({ detail, readOnly = false }: { detail: Family; readOnly?: boolean }) {
  const [variantId, setVariantId] = useState<string>("");
  const [editing, setEditing] = useState<Target | null>(null);
  const [adding, setAdding] = useState(false);
  const variant = detail.variants.find((v) => v.variant_id === variantId) ?? detail.variants[0];
  const added = useFamilySaved(() => {
    setAdding(false);
  });
  const active = useVariantActive(added);

  return (
    <>
      {detail.reading && (
        <p className="mt-4 text-sm">
          <Badge tone="info">being read</Badge> The catalog text is being read for further values.
        </p>
      )}
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card>
          <CardTitle>For the whole family</CardTitle>
          <ValuesTable
            family={detail}
            values={detail.family_values}
            unavailable={detail.family_unavailable}
            own={(key) => detail.own_facts.find((f) => f.attribute_key === key && !f.variant_id)}
            scopeColumn={false}
            action={readOnly ? undefined : "Edit"}
            onEdit={(attribute) => {
              setEditing({
                attribute,
                familyId: detail.id,
                label: `${attribute.label} · whole family`,
              });
            }}
          />
        </Card>
        {(variant ?? !readOnly) && (
          <Card>
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <CardTitle className="mb-0">One variant</CardTitle>
              {!readOnly && (
                <div className="flex gap-2">
                  <Button
                    size="sm"
                    variant="secondary"
                    onClick={() => {
                      setAdding(true);
                    }}
                  >
                    Add variant
                  </Button>
                  {variant && (
                    <Button
                      size="sm"
                      variant={variant.is_active ? "danger" : "secondary"}
                      disabled={active.isPending}
                      onClick={() => {
                        active.mutate(variant);
                      }}
                    >
                      {variant.is_active ? "Retire" : "Reactivate"}
                    </Button>
                  )}
                </div>
              )}
            </div>
            {!variant ? (
              <Empty>No variants yet.</Empty>
            ) : (
              <>
                <div className="mb-3 w-72">
                  <Label htmlFor="variant" className="text-xs">
                    Variant
                  </Label>
                  <Select
                    id="variant"
                    value={variant.variant_id}
                    onChange={(event) => {
                      setVariantId(event.target.value);
                    }}
                  >
                    {detail.variants.map((v) => (
                      <option key={v.variant_id} value={v.variant_id}>
                        {v.article_no} · {v.label}
                        {v.is_active ? "" : " (retired)"}
                      </option>
                    ))}
                  </Select>
                </div>
                {!variant.is_active && (
                  <p className="mb-3 text-sm">
                    <Badge>retired</Badge> Out of search and new assessments; open ones keep it.
                  </p>
                )}
                <ValuesTable
                  family={detail}
                  values={variant.values}
                  unavailable={variant.unavailable}
                  own={(key) =>
                    detail.own_facts.find(
                      (f) => f.attribute_key === key && f.variant_id === variant.variant_id,
                    )
                  }
                  scopeColumn
                  action={readOnly ? undefined : "Override"}
                  onEdit={(attribute) => {
                    setEditing({
                      attribute,
                      variantId: variant.variant_id,
                      label: `${attribute.label} · ${variant.article_no} only`,
                    });
                  }}
                />
              </>
            )}
            <ErrorMessage error={active.error} />
          </Card>
        )}
      </div>
      {adding && (
        <VariantDialog
          family={detail}
          onSaved={added}
          onClose={() => {
            setAdding(false);
          }}
        />
      )}
      {editing && (
        <EditDialog
          familyKey={detail.id}
          target={editing}
          onClose={() => {
            setEditing(null);
          }}
        />
      )}
    </>
  );
}

function ValuesTable({
  family,
  values,
  unavailable,
  own,
  scopeColumn,
  action,
  onEdit,
}: {
  family: Family;
  values: Record<string, Value>;
  unavailable: string[];
  own: (key: string) => OwnFact | undefined;
  scopeColumn: boolean;
  /** No action: the table is read only. */
  action?: string | undefined;
  onEdit: (attribute: Attribute) => void;
}) {
  const withdraw = useWithdraw(family.id);
  return (
    <>
      <Table>
        <thead>
          <tr>
            <Th>Attribute</Th>
            <Th>Value</Th>
            <Th>Source</Th>
            {scopeColumn && <Th>Applies to</Th>}
            {action && <Th />}
          </tr>
        </thead>
        <tbody>
          {family.attributes.map((attribute) => {
            const value = values[attribute.key];
            const mine = own(attribute.key);
            return (
              <tr key={attribute.key}>
                <Td>
                  {attribute.label} <CriticalityBadge criticality={attribute.criticality} />
                </Td>
                <Td>
                  {unavailable.includes(attribute.key) ? (
                    <Badge>not available</Badge>
                  ) : (
                    <ValueView value={value?.value} />
                  )}
                </Td>
                <Td className="text-xs text-neutral-500">
                  {value ? (SOURCE[value.source] ?? value.source) : "–"}
                </Td>
                {scopeColumn && (
                  <Td className="text-xs text-neutral-500">
                    {value?.scope === "VARIANT" ? "this variant" : value ? "family" : "–"}
                  </Td>
                )}
                {action && (
                  <Td className="space-x-1 text-right whitespace-nowrap">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        onEdit(attribute);
                      }}
                    >
                      {action}
                    </Button>
                    {mine && (
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={withdraw.isPending}
                        onClick={() => {
                          withdraw.mutate(mine.fact_id);
                        }}
                      >
                        {scopeColumn ? "Remove override" : "Withdraw"}
                      </Button>
                    )}
                  </Td>
                )}
              </tr>
            );
          })}
        </tbody>
      </Table>
      <ErrorMessage error={withdraw.error} />
    </>
  );
}

function useVariantActive(onSaved: (saved: Family) => void) {
  const { session } = useSession();
  return useMutation({
    mutationFn: (variant: Family["variants"][number]) =>
      session.call((hub) => {
        const params = { params: { path: { variant_id: variant.variant_id } } };
        return variant.is_active
          ? hub.POST("/api/v1/supplier/catalog/variants/{variant_id}/retire", params)
          : hub.POST("/api/v1/supplier/catalog/variants/{variant_id}/reactivate", params);
      }),
    onSuccess: onSaved,
  });
}

function useWithdraw(familyId: string) {
  const { session } = useSession();
  const queries = useQueryClient();
  return useMutation({
    mutationFn: (factId: string) =>
      session.call((hub) =>
        hub.DELETE("/api/v1/supplier/catalog/facts/{fact_id}", {
          params: { path: { fact_id: factId } },
        }),
      ),
    onSuccess: () => queries.invalidateQueries({ queryKey: ["family", familyId] }),
  });
}

function EditDialog({
  familyKey,
  target,
  onClose,
}: {
  familyKey: string;
  target: Target;
  onClose: () => void;
}) {
  const { session } = useSession();
  const queries = useQueryClient();
  const [value, setValue] = useState<TypedValue | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const save = useMutation({
    mutationFn: () =>
      session.call((hub) =>
        hub.PUT("/api/v1/supplier/catalog/facts", {
          body: {
            family_id: target.familyId ?? null,
            variant_id: target.variantId ?? null,
            attribute_key: target.attribute.key,
            value: unavailable ? null : (value as never),
            unavailable,
          },
        }),
      ),
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: ["family", familyKey] });
      onClose();
    },
  });
  const { attribute } = target;
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={target.label}
      footer={
        <Button
          disabled={save.isPending || (!unavailable && value === null)}
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
          label={attribute.label}
          expected={{
            type: attribute.type,
            ...(attribute.unit ? { unit: attribute.unit } : {}),
            ...(attribute.options.length ? { options: attribute.options } : {}),
          }}
          value={value}
          disabled={unavailable}
          onChange={setValue}
        />
        <Label className="flex items-center gap-2 font-normal">
          <input
            type="checkbox"
            checked={unavailable}
            onChange={(event) => {
              setUnavailable(event.target.checked);
            }}
          />
          Not available for this product
        </Label>
        <ErrorMessage error={save.error} />
      </div>
    </Dialog>
  );
}
