import type { HubSchemas } from "@sanovio/api";
import { useQuery } from "@tanstack/react-query";

import { useSession } from "../sessionContext";

export type AssessmentDetail = HubSchemas["schemas"]["AssessmentDetail"];
export type Question = HubSchemas["schemas"]["QuestionView"];
export type Round = HubSchemas["schemas"]["RoundView"];

/** States in which the hub is still working; the page polls until it is done (§20). */
const BUSY = new Set(["ASSESSING", "AWAITING_ANSWERS"]);

export function useAssessment(assessmentId: string) {
  const { session } = useSession();
  return useQuery({
    queryKey: ["hub", "assessment", assessmentId],
    queryFn: () =>
      session.atHub((hub) =>
        hub.GET("/api/v1/assessments/{assessment_id}", {
          params: { path: { assessment_id: assessmentId } },
        }),
      ),
    refetchInterval: (query) => (BUSY.has(query.state.data?.status ?? "") ? 2_000 : false),
  });
}

export function useAssessments(filters: { status?: string; mine: boolean }) {
  const { session } = useSession();
  return useQuery({
    queryKey: ["hub", "assessments", filters],
    queryFn: () =>
      session.atHub((hub) =>
        hub.GET("/api/v1/assessments", {
          params: {
            query: {
              ...(filters.status ? { status: filters.status } : {}),
              ...(filters.mine ? { assigned_to: "me" } : {}),
            },
          },
        }),
      ),
    refetchInterval: 10_000,
  });
}
