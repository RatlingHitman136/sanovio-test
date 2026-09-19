import type { HubSchemas } from "@sanovio/api";
import { Button, Dialog, ErrorMessage, Input, Label, Notice, Select, Textarea } from "@sanovio/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { useSession } from "../sessionContext";

type Family = HubSchemas["schemas"]["SupplierFamilyDetail"];
type FamilyText = HubSchemas["schemas"]["FamilyTextBody"];
type VariantBody = HubSchemas["schemas"]["VariantCreate"];

const TEXT_FIELDS: { name: keyof FamilyText; label: string; long?: boolean }[] = [
  { name: "name", label: "Name" },
  { name: "manufacturer", label: "Manufacturer" },
  { name: "brand_name", label: "Brand" },
  { name: "product_type", label: "Product type" },
  { name: "description", label: "Description", long: true },
  { name: "properties_text", label: "Properties", long: true },
];

function Field({ label, id, children }: { label: string; id: string; children: ReactNode }) {
  return (
    <div className="space-y-1">
      <Label htmlFor={id}>{label}</Label>
      {children}
    </div>
  );
}

function blankToNull(value: string): string | null {
  return value.trim() === "" ? null : value.trim();
}

/** A new family (no `family`) or an edit of one. A changed text is read again (§9). */
export function FamilyDialog({
  family,
  manufacturer,
  onSaved,
  onClose,
}: {
  family?: Family;
  manufacturer: string;
  onSaved: (saved: Family) => void;
  onClose: () => void;
}) {
  const { session } = useSession();
  const categories = useQuery({
    queryKey: ["templates"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/templates")),
  });
  const [text, setText] = useState<Record<keyof FamilyText, string>>(() => ({
    name: family?.name ?? "",
    manufacturer: family?.manufacturer ?? manufacturer,
    brand_name: family?.brand_name ?? "",
    product_type: family?.product_type ?? "",
    description: family?.description ?? "",
    properties_text: family?.properties_text ?? "",
  }));
  const [category, setCategory] = useState(family?.category_code ?? "");
  const body: FamilyText = {
    name: text.name.trim(),
    manufacturer: text.manufacturer.trim(),
    brand_name: blankToNull(text.brand_name),
    product_type: blankToNull(text.product_type),
    description: blankToNull(text.description),
    properties_text: blankToNull(text.properties_text),
  };
  const save = useMutation({
    mutationFn: () =>
      session.call((hub) =>
        family
          ? hub.PATCH("/api/v1/supplier/catalog/families/{family_id}", {
              params: { path: { family_id: family.id } },
              body: {
                text: body,
                category_code: category === family.category_code ? null : category,
              },
            })
          : hub.POST("/api/v1/supplier/catalog/families", {
              body: { ...body, category_code: category },
            }),
      ),
    onSuccess: onSaved,
  });

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={family ? `Edit ${family.name}` : "New family"}
      footer={
        <Button
          disabled={!body.name || !body.manufacturer || !category || save.isPending}
          onClick={() => {
            save.mutate();
          }}
        >
          Save
        </Button>
      }
    >
      <div className="space-y-3">
        <Notice>
          The text is read for values: at once for the headline, in the background for the
          description. A changed text replaces what the old text said.
        </Notice>
        <Field label="Category" id="category">
          <Select
            id="category"
            value={category}
            onChange={(event) => {
              setCategory(event.target.value);
            }}
          >
            <option value="">Choose…</option>
            {(categories.data ?? []).map((template) => (
              <option key={template.code} value={template.code}>
                {template.code}
              </option>
            ))}
          </Select>
        </Field>
        {TEXT_FIELDS.map(({ name, label, long }) => {
          const Control = long ? Textarea : Input;
          return (
            <Field key={name} label={label} id={name}>
              <Control
                id={name}
                value={text[name]}
                onChange={(event: { target: { value: string } }) => {
                  setText({ ...text, [name]: event.target.value });
                }}
              />
            </Field>
          );
        })}
        <ErrorMessage error={save.error} />
      </div>
    </Dialog>
  );
}

type RowForm = Record<keyof VariantBody, string>;

const ROW_FIELDS: { name: keyof VariantBody; label: string; numeric?: boolean }[] = [
  { name: "article_no", label: "Article no." },
  { name: "label", label: "Label" },
  { name: "size_text", label: "Size, as printed (e.g. 20 ml, 0,80 x 40 mm 21G)" },
  { name: "order_unit", label: "Order unit" },
  { name: "units_per_order_unit", label: "Units per order unit", numeric: true },
  { name: "order_units_per_shipping_unit", label: "Order units per shipping unit", numeric: true },
  { name: "gtin", label: "GTIN" },
  { name: "pzn", label: "PZN" },
];

const EMPTY_ROW: RowForm = {
  article_no: "",
  label: "",
  size_text: "",
  order_unit: "",
  units_per_order_unit: "",
  order_units_per_shipping_unit: "",
  gtin: "",
  pzn: "",
};

/** A sibling's row without what identifies one article: its number, GTIN and PZN. */
function copyOf(variant: Family["variants"][number]): RowForm {
  return {
    ...EMPTY_ROW,
    label: variant.label,
    size_text: variant.size_text ?? "",
    order_unit: variant.order_unit ?? "",
    units_per_order_unit: variant.units_per_order_unit?.toString() ?? "",
    order_units_per_shipping_unit: variant.order_units_per_shipping_unit?.toString() ?? "",
  };
}

function number(value: string): number | null {
  return value.trim() === "" ? null : Number(value);
}

/** A new article in the family, entered as its size-table row and read by the parsers. */
export function VariantDialog({
  family,
  onSaved,
  onClose,
}: {
  family: Family;
  onSaved: (saved: Family) => void;
  onClose: () => void;
}) {
  const { session } = useSession();
  const [row, setRow] = useState<RowForm>(EMPTY_ROW);
  const add = useMutation({
    mutationFn: () =>
      session.call((hub) =>
        hub.POST("/api/v1/supplier/catalog/families/{family_id}/variants", {
          params: { path: { family_id: family.id } },
          body: {
            article_no: row.article_no.trim(),
            label: row.label.trim(),
            size_text: blankToNull(row.size_text),
            order_unit: blankToNull(row.order_unit),
            units_per_order_unit: number(row.units_per_order_unit),
            order_units_per_shipping_unit: number(row.order_units_per_shipping_unit),
            gtin: blankToNull(row.gtin),
            pzn: blankToNull(row.pzn),
          },
        }),
      ),
    onSuccess: onSaved,
  });

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={`New variant of ${family.name}`}
      footer={
        <Button
          disabled={!row.article_no.trim() || !row.label.trim() || add.isPending}
          onClick={() => {
            add.mutate();
          }}
        >
          Add
        </Button>
      }
    >
      <div className="space-y-3">
        {family.variants.length > 0 && (
          <Field label="Copy from" id="copy-from">
            <Select
              id="copy-from"
              defaultValue=""
              onChange={(event) => {
                const source = family.variants.find((v) => v.variant_id === event.target.value);
                if (source) setRow(copyOf(source));
              }}
            >
              <option value="">Start empty</option>
              {family.variants.map((v) => (
                <option key={v.variant_id} value={v.variant_id}>
                  {v.article_no} · {v.label}
                </option>
              ))}
            </Select>
          </Field>
        )}
        <div className="grid grid-cols-2 gap-3">
          {ROW_FIELDS.map(({ name, label, numeric }) => (
            <Field key={name} label={label} id={name}>
              <Input
                id={name}
                inputMode={numeric ? "numeric" : undefined}
                value={row[name]}
                onChange={(event) => {
                  setRow({ ...row, [name]: event.target.value });
                }}
              />
            </Field>
          ))}
        </div>
        <p className="text-xs text-neutral-500">
          Every other value is set afterwards, on this page, for the family or for this variant.
        </p>
        <ErrorMessage error={add.error} />
      </div>
    </Dialog>
  );
}
