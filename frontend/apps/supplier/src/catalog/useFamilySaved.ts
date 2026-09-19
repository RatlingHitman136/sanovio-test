import type { HubSchemas } from "@sanovio/api";
import { useQueryClient } from "@tanstack/react-query";

type Family = HubSchemas["schemas"]["SupplierFamilyDetail"];

/** Stores the page's new state after any family or variant change. */
export function useFamilySaved(onDone: () => void): (saved: Family) => void {
  const queries = useQueryClient();
  return (saved) => {
    queries.setQueryData(["family", saved.id], saved);
    void queries.invalidateQueries({ queryKey: ["catalog"] });
    onDone();
  };
}
