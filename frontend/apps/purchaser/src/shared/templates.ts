import type { ExpectedAnswer } from "@sanovio/ui";
import { useQuery } from "@tanstack/react-query";

import { useSession } from "../sessionContext";

export interface TemplateAttribute {
  key: string;
  type: string;
  unit?: string | null;
  options?: string[];
  criticality: string;
  labels: { de: string; en: string };
}

export interface TemplateDefinition {
  code: string;
  attributes: TemplateAttribute[];
}

/** The category templates installed at this node, by code. */
export function useTemplates() {
  const { session } = useSession();
  return useQuery({
    queryKey: ["node", "templates"],
    queryFn: async () => {
      const rows = await session.atNode((node) => node.GET("/api/v1/templates"));
      return new Map(
        rows.map((row) => [row.code, row.definition as unknown as TemplateDefinition]),
      );
    },
    staleTime: Infinity,
  });
}

/** What an answer for `key` must look like, from the template definition. */
export function expectedFor(template: TemplateDefinition | undefined, key: string): ExpectedAnswer {
  const attribute = template?.attributes.find((entry) => entry.key === key);
  if (!attribute) return { type: "text" };
  return {
    type: attribute.type,
    ...(attribute.unit ? { unit: attribute.unit } : {}),
    ...(attribute.options?.length ? { options: attribute.options } : {}),
  };
}

export function labelFor(template: TemplateDefinition | undefined, key: string): string {
  return template?.attributes.find((entry) => entry.key === key)?.labels.en ?? key;
}
