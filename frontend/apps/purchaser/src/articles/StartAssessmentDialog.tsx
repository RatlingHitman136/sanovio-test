import { ApiError } from "@sanovio/api";
import { Button, Dialog, ErrorMessage, Spinner } from "@sanovio/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router";

import { useSession } from "../sessionContext";
import { RequirementPanel } from "../shared/RequirementPanel";
import { issueRequirement } from "../shared/requirements";
import type { Article } from "./queries";
import type { Candidate } from "./SearchCard";

/** Shows the requirement that will leave the hospital, then opens the assessment (§19 step 4). */
export function StartAssessmentDialog({
  article,
  candidate,
  onClose,
}: {
  article: Article;
  candidate: Candidate;
  onClose: () => void;
}) {
  const { session } = useSession();
  const navigate = useNavigate();
  const requirement = useQuery({
    queryKey: ["requirement", article.id, candidate.variant_id],
    queryFn: () => issueRequirement(session, article.id),
    gcTime: 0,
  });
  const start = useMutation({
    mutationFn: async () => {
      if (!requirement.data) throw new Error("no requirement yet");
      try {
        const opened = await session.atHub((hub) =>
          hub.POST("/api/v1/assessments", {
            body: { requirement: requirement.data, variant_id: candidate.variant_id },
          }),
        );
        return opened.id;
      } catch (error) {
        // Already open for this article and product: go there instead (§14).
        if (error instanceof ApiError && error.code === "ASSESSMENT_OPEN") {
          return String(error.body.assessment_id);
        }
        throw error;
      }
    },
    onSuccess: (assessmentId) => {
      void navigate(`/assessments/${assessmentId}`);
    },
  });
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={`Assess ${candidate.display_name}`}
      footer={
        <Button
          disabled={!requirement.data || start.isPending}
          onClick={() => {
            start.mutate();
          }}
        >
          Start assessment
        </Button>
      }
    >
      <div className="space-y-3 text-sm">
        <p>
          The hub compares this requirement with {candidate.supplier}&apos;s product, asks what is
          missing, and proposes a verdict.
        </p>
        {requirement.isPending ? <Spinner /> : <RequirementPanel requirement={requirement.data} />}
        <ErrorMessage error={requirement.error ?? start.error} />
      </div>
    </Dialog>
  );
}
