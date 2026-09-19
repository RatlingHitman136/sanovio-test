import type { HubSchemas } from "@sanovio/api";

type Family = HubSchemas["schemas"]["SupplierFamilyDetail"];

/** One family as the hub serves it, with a family value and a variant override. */
export const family: Family = {
  id: "fam-1",
  name: "BD Plastipak™ Luer-Lok™",
  category_code: "syringe_single_use",
  attributes: [
    {
      key: "dehp_free",
      label: "DEHP-free",
      type: "bool",
      unit: null,
      options: [],
      criticality: "major",
    },
    {
      key: "special_scale",
      label: "Special scale",
      type: "text",
      unit: null,
      options: [],
      criticality: "major",
    },
  ],
  family_values: {
    dehp_free: {
      value: { type: "bool", value: true },
      source: "CATALOG",
      scope: "FAMILY",
      fact_id: "c1",
    },
  },
  family_unavailable: [],
  variants: [
    {
      variant_id: "var-10",
      article_no: "300912",
      label: "BD Plastipak™ Luer-Lok™ 10 ml",
      values: {
        dehp_free: {
          value: { type: "bool", value: true },
          source: "CATALOG",
          scope: "FAMILY",
          fact_id: "c1",
        },
        special_scale: {
          value: { type: "text", value: "Insulin" },
          source: "SUPPLIER_ANSWER",
          scope: "VARIANT",
          fact_id: "o1",
        },
      },
      unavailable: [],
    },
  ],
  own_facts: [
    {
      fact_id: "o1",
      attribute_key: "special_scale",
      variant_id: "var-10",
      value: { type: "text", value: "Insulin" },
      unavailable: false,
    },
  ],
};
