/** Responses shaped by the generated schemas: a wrong field fails to compile. */
import type { HubSchemas, NodeSchemas } from "@sanovio/api";

type N = NodeSchemas["schemas"];
type H = HubSchemas["schemas"];

export const NODE = "http://node.test";
export const HUB = "http://hub.test";

export const me: N["Me"] = {
  display_name: "Anna Meier",
  email: "anna.meier@demo-ksp.example",
  hub_subject_id: "sub_7QF2M4XK9P3TZC8W1N6R",
  role: "PURCHASER",
};

const syringeTemplate = {
  code: "syringe_single_use",
  attributes: [
    {
      key: "nominal_volume_ml",
      type: "number",
      unit: "ml",
      options: [],
      criticality: "critical",
      labels: { de: "Nennvolumen", en: "Nominal volume" },
    },
    {
      key: "connector",
      type: "enum",
      unit: null,
      options: ["LUER", "LUER_LOCK"],
      criticality: "critical",
      labels: { de: "Konus", en: "Connector" },
    },
    {
      key: "design",
      type: "enum",
      unit: null,
      options: ["TWO_PART", "THREE_PART"],
      criticality: "major",
      labels: { de: "Bauart", en: "Design" },
    },
  ],
};

export const templates: N["InstalledTemplateView"][] = [
  {
    code: "syringe_single_use",
    definition: syringeTemplate,
    definition_hash: "a1",
    updated_at: "2026-09-19T08:00:00Z",
    installed_at: "2026-09-19T08:00:00Z",
  },
];

export const articleSummary: N["ArticleSummary"] = {
  id: "art-3",
  internal_id: "3",
  article_ref: "ar_5MZQ4K7T2V9C",
  name: "Einmalspritze 10 ml Luer-Lock steril",
  brand: "B. Braun",
  category_code: "syringe_single_use",
  category_source: "LLM_SUGGESTED",
  data_quality_issues: ["GTIN_EAN_MISMATCH"],
};

export const article: N["ArticleDetail"] = {
  ...articleSummary,
  annual_quantity: 12000,
  order_unit: "Karton",
  base_units_per_order_unit: 100,
  base_unit: "Stück",
  target_net_price: "0.12",
  currency: "CHF",
  category_set_at: null,
  attributes: [
    {
      key: "nominal_volume_ml",
      value: { type: "number", value: 10, unit: "ml" },
      source: "EXTRACTION",
      method: "RULES",
      quote: "10 ml",
      fact_id: "f1",
    },
    {
      key: "design",
      value: { type: "enum", value: "THREE_PART" },
      source: "PURCHASER_ANSWER",
      method: null,
      quote: null,
      fact_id: "f2",
    },
  ],
  unknown_attributes: ["connector"],
  unavailable_attributes: [],
  identifiers: [{ scheme: "GTIN", value: "04022495123456", checksum_valid: false }],
  reference: null,
  requirement_hash: null,
};

export const requirement = {
  requirement_version: 1,
  article_ref: "ar_5MZQ4K7T2V9C",
  template_code: "syringe_single_use",
  attributes: { nominal_volume_ml: { type: "number", value: 10, unit: "ml" } },
  attribute_origin: { nominal_volume_ml: "EXTRACTED" },
  unknown_attributes: ["connector"],
  unavailable_attributes: [],
  withheld_attributes: [],
  answered_question_ids: [],
  product_hints: null,
  limited_template: false,
} satisfies H["RequirementPayload"];

export const injekt: H["CandidateView"] = {
  variant_id: "var-injekt",
  article_no: "4606728V",
  display_name: "Injekt® Luer Lock Solo 10 ml (4606728V)",
  supplier: "B. Braun",
  family: "Injekt® Luer Lock Solo",
  manufacturer: "B. Braun",
  score: 0.92,
  coverage: 0.8,
  critical_unknowns: 1,
  identifier_match: null,
  precheck: [
    {
      attribute_key: "nominal_volume_ml",
      criticality: "critical",
      status: "MATCH",
      supplier_value: { type: "number", value: 10, unit: "ml" },
    },
  ],
  additional_information: {},
};

export const plastipak: H["CandidateView"] = {
  ...injekt,
  variant_id: "var-plastipak",
  article_no: "300912",
  display_name: "BD Plastipak™ Luer-Lok™ 10 ml (300912)",
  supplier: "BD",
  family: "BD Plastipak™ Luer-Lok™",
  manufacturer: "BD",
  score: 0.88,
};

export function searchResponse(hardFilters: number): H["SearchResponse"] {
  const filters = { nominal_volume_ml: { type: "number", value: 10, unit: "ml" } };
  return {
    search_spec: {
      category: "syringe_single_use",
      hard_filters:
        hardFilters > 1 ? { ...filters, connector: { type: "enum", value: "LUER_LOCK" } } : filters,
      soft_criteria: [],
      hospital_gaps: ["connector"],
    },
    hospital_gaps: ["connector"],
    excluded_by: { connector: 2 },
    candidates: [injekt, plastipak],
  };
}

export const injektAttributes: H["VariantAttributesView"] = {
  variant_id: "var-injekt",
  label: "Injekt® Luer Lock Solo 10 ml (4606728V)",
  attributes: {
    connector: { value: { type: "enum", value: "LUER_LOCK" }, fact_id: "h1" },
    design: { value: { type: "enum", value: "TWO_PART" }, fact_id: "h2" },
  },
  identifiers: [],
  additional_information: {},
};

export const preview: N["PreviewView"] = {
  fills: [{ key: "connector", value: { type: "enum", value: "LUER_LOCK" } }],
  conflicts: [
    {
      key: "design",
      ours: { type: "enum", value: "THREE_PART" },
      ours_source: "PURCHASER_ANSWER",
      theirs: { type: "enum", value: "TWO_PART" },
    },
  ],
  kept_purchaser: [],
  identifiers_info: {},
  ignored: [],
};

export const colleagues: N["UserEntry"][] = [
  {
    display_name: "Anna Meier",
    hub_subject_id: me.hub_subject_id,
    role: "PURCHASER",
    is_active: true,
  },
  {
    display_name: "Beat Keller",
    hub_subject_id: "sub_2B7Q9M3X5K8T1Z4W6N0R",
    role: "PURCHASER",
    is_active: true,
  },
];

const round1: H["RoundView"] = {
  round_no: 1,
  identifier_evidence: "NO_INFORMATION",
  rule_verdict: "INSUFFICIENT_DATA",
  llm_verdict: "INSUFFICIENT_DATA",
  disagreement: false,
  rationale: "Blocking information is missing.",
  outcome_status: "NEEDS_QUESTION_REVIEW",
  attribute_judgments: [
    {
      attribute_key: "nominal_volume_ml",
      criticality: "critical",
      rule: "exact",
      status: "MATCH",
      decided_by: "COMPARATOR",
      hospital: { value: { type: "number", value: 10, unit: "ml" }, origin: "EXTRACTED" },
      supplier: {
        value: { type: "number", value: 10, unit: "ml" },
        fact_id: "s1",
        scope: "VARIANT",
      },
    },
    {
      attribute_key: "design",
      criticality: "major",
      rule: "exact",
      status: "MISMATCH",
      decided_by: "COMPARATOR",
      hospital: { value: { type: "enum", value: "TWO_PART" }, origin: "REFERENCE" },
      supplier: { value: { type: "enum", value: "THREE_PART" }, fact_id: "s2", scope: "FAMILY" },
    },
  ],
};

export const supplierDraft: H["QuestionView"] = {
  id: "q-supplier",
  addressee: "SUPPLIER",
  attribute_key: "mdr_class",
  text: "In welche MDR-Risikoklasse ist die BD Plastipak eingestuft?",
  language: "de",
  expected_answer: { type: "enum", options: ["I", "IIA", "IIB"] },
  rationale: null,
  origin: "LLM",
  status: "DRAFT",
  answer: null,
};

export const purchaserDraft: H["QuestionView"] = {
  id: "q-purchaser",
  addressee: "PURCHASER",
  attribute_key: "connector",
  text: "Which connector does your current syringe have?",
  language: "en",
  expected_answer: { type: "enum", options: ["LUER", "LUER_LOCK"] },
  rationale: null,
  origin: "TEMPLATE",
  status: "DRAFT",
  answer: null,
};

export function assessment(overrides: Partial<H["AssessmentDetail"]> = {}): H["AssessmentDetail"] {
  return {
    id: "asm-1",
    article_ref: articleSummary.article_ref,
    variant_id: "var-plastipak",
    article_no: "300912",
    variant_label: "BD Plastipak™ Luer-Lok™ 10 ml",
    supplier: "BD",
    status: "NEEDS_QUESTION_REVIEW",
    current_round: 1,
    proposed_verdict: null,
    final_verdict: null,
    version: 4,
    created_by_subject_id: me.hub_subject_id,
    assigned_to_subject_id: "sub_2B7Q9M3X5K8T1Z4W6N0R",
    created_at: "2026-09-19T09:00:00Z",
    template_code: "syringe_single_use",
    manual_reason: null,
    resolution_kind: null,
    resolution_note: null,
    resolved_by_subject_id: null,
    rounds: [round1],
    questions: [supplierDraft, purchaserDraft],
    events: [],
    ...overrides,
  };
}

export function summaryOf(detail: H["AssessmentDetail"]): H["AssessmentSummary"] {
  return {
    id: detail.id,
    article_ref: detail.article_ref,
    variant_id: detail.variant_id,
    article_no: detail.article_no,
    variant_label: detail.variant_label,
    supplier: detail.supplier,
    status: detail.status,
    current_round: detail.current_round,
    proposed_verdict: detail.proposed_verdict,
    final_verdict: detail.final_verdict,
    version: detail.version,
    created_by_subject_id: detail.created_by_subject_id,
    assigned_to_subject_id: detail.assigned_to_subject_id,
    created_at: detail.created_at,
  };
}
