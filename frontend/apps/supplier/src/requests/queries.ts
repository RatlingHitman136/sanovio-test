import type { HubSchemas } from "@sanovio/api";
import { useQuery } from "@tanstack/react-query";

import { useSession } from "../sessionContext";

export type SupplierRequest = HubSchemas["schemas"]["SupplierRequestView"];
export type SupplierQuestion = HubSchemas["schemas"]["SupplierQuestionView"];

export function useRequests() {
  const { session } = useSession();
  return useQuery({
    queryKey: ["requests"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/supplier/requests")),
    refetchInterval: 15_000,
  });
}

export function useRequest(assessmentId: string) {
  const { session } = useSession();
  return useQuery({
    queryKey: ["requests", assessmentId],
    queryFn: () =>
      session.call((hub) =>
        hub.GET("/api/v1/supplier/requests/{assessment_id}", {
          params: { path: { assessment_id: assessmentId } },
        }),
      ),
  });
}
