import { Button, Dialog, ErrorMessage, Label, Select, Textarea } from "@sanovio/ui";
import { useState } from "react";

import { useSession } from "../sessionContext";
import type { AssessmentDetail } from "./queries";
import { useAction } from "./useAction";

const VERDICTS = ["EQUIVALENT", "EQUIVALENT_WITH_DEVIATIONS", "NOT_EQUIVALENT"] as const;
type Verdict = (typeof VERDICTS)[number] | "UNDETERMINED";
type SimpleAction = "request-more-info" | "extra-round" | "retry" | "cancel";

const FINAL = new Set(["RESOLVED", "CANCELLED"]);

/** Only what the state machine allows from the current status is offered (§11). */
export function Actions({ assessment }: { assessment: AssessmentDetail }) {
  const { session } = useSession();
  const [resolving, setResolving] = useState<"confirm" | "override" | "manual" | null>(null);
  const simple = useAction(assessment.id, (action: SimpleAction) =>
    session.atHub((hub) =>
      hub.POST(`/api/v1/assessments/{assessment_id}/${action}`, {
        params: { path: { assessment_id: assessment.id } },
        body: { version: assessment.version },
      }),
    ),
  );
  if (FINAL.has(assessment.status)) return null;

  const button = (
    label: string,
    action: SimpleAction,
    variant: "secondary" | "danger" = "secondary",
  ) => (
    <Button
      variant={variant}
      size="sm"
      disabled={simple.isPending}
      onClick={() => {
        simple.mutate(action);
      }}
    >
      {label}
    </Button>
  );

  return (
    <div className="flex flex-wrap items-center gap-2">
      {assessment.status === "PROPOSED_RESOLUTION" && (
        <>
          <Button
            size="sm"
            onClick={() => {
              setResolving("confirm");
            }}
          >
            Confirm verdict
          </Button>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              setResolving("override");
            }}
          >
            Override
          </Button>
          {button("Ask more questions", "request-more-info")}
        </>
      )}
      {assessment.status === "NEEDS_MANUAL_DECISION" && (
        <>
          <Button
            size="sm"
            onClick={() => {
              setResolving("manual");
            }}
          >
            Decide
          </Button>
          {button("One more round", "extra-round")}
        </>
      )}
      {assessment.status === "FAILED" && button("Retry", "retry")}
      {button("Cancel assessment", "cancel", "danger")}
      <ErrorMessage error={simple.error} />
      {resolving && (
        <ResolveDialog
          assessment={assessment}
          mode={resolving}
          onClose={() => {
            setResolving(null);
          }}
        />
      )}
    </div>
  );
}

export function ResolveDialog({
  assessment,
  mode,
  presetNote = "",
  presetVerdict,
  onClose,
}: {
  assessment: AssessmentDetail;
  mode: "confirm" | "override" | "manual";
  presetNote?: string;
  presetVerdict?: Verdict;
  onClose: () => void;
}) {
  const { session } = useSession();
  const proposed = assessment.proposed_verdict as Verdict | null;
  const [verdict, setVerdict] = useState<Verdict>(
    presetVerdict ?? (mode === "confirm" && proposed ? proposed : "NOT_EQUIVALENT"),
  );
  const [note, setNote] = useState(presetNote);
  const resolve = useAction(assessment.id, () =>
    session.atHub((hub) =>
      hub.POST("/api/v1/assessments/{assessment_id}/resolve", {
        params: { path: { assessment_id: assessment.id } },
        body: { verdict, note: note.trim() || null, version: assessment.version },
      }),
    ),
  );
  const overriding = mode !== "confirm" && verdict !== proposed;
  const choices: Verdict[] = mode === "manual" ? [...VERDICTS, "UNDETERMINED"] : [...VERDICTS];
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={mode === "confirm" ? "Confirm the proposed verdict" : "Decide the verdict"}
      footer={
        <Button
          disabled={resolve.isPending || (overriding && mode === "override" && !note.trim())}
          onClick={() => {
            resolve.mutate(undefined, { onSuccess: onClose });
          }}
        >
          Resolve
        </Button>
      }
    >
      <div className="space-y-3">
        <Label htmlFor="verdict">Verdict</Label>
        <Select
          id="verdict"
          value={verdict}
          disabled={mode === "confirm"}
          onChange={(event) => {
            setVerdict(event.target.value as Verdict);
          }}
        >
          {choices.map((code) => (
            <option key={code} value={code}>
              {code.replaceAll("_", " ").toLowerCase()}
            </option>
          ))}
        </Select>
        <Label htmlFor="note">
          Note {mode === "override" && overriding ? "(required when overriding)" : "(optional)"}
        </Label>
        <Textarea
          id="note"
          value={note}
          onChange={(event) => {
            setNote(event.target.value);
          }}
        />
        <ErrorMessage error={resolve.error} />
      </div>
    </Dialog>
  );
}
