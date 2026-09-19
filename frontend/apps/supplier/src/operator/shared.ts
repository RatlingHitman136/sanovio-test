import type { HubSchemas } from "@sanovio/api";

export type Criticality = HubSchemas["schemas"]["Criticality"];
export type Rule = HubSchemas["schemas"]["ComparisonRule"];
export type RuleSettings = HubSchemas["schemas"]["RuleSettings"];

export const CRITICALITIES: Criticality[] = ["critical", "major", "minor"];

// Which rule fits which value type is checked by the hub; this is only the choice offered.
export const RULES: Rule[] = [
  "exact",
  "tolerance",
  "same_or_finer",
  "same_or_more",
  "includes",
  "required_if_hospital",
  "semantic",
  "info_only",
  "derived",
];

export function when(iso: string | null | undefined): string {
  return iso ? new Date(iso).toLocaleString("en-GB") : "–";
}

export function usd(amount: string | number): string {
  return `$${Number(amount).toFixed(4)}`;
}
