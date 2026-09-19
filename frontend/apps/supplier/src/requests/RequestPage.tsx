import {
  Badge,
  Button,
  Card,
  ErrorMessage,
  Label,
  Notice,
  PageHeader,
  Spinner,
  StatusBadge,
  Textarea,
  ValueInput,
  ValueView,
  type ExpectedAnswer,
  type TypedValue,
} from "@sanovio/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";

import { useSession } from "../sessionContext";
import { useRequest, type SupplierQuestion, type SupplierRequest } from "./queries";

interface Draft {
  value: TypedValue | null;
  comment: string;
  cannotProvide: boolean;
  appliesToFamily: boolean;
}

function initial(question: SupplierQuestion): Draft {
  const saved = question.draft;
  return {
    value: (saved?.value as TypedValue | null | undefined) ?? null,
    comment: typeof saved?.comment === "string" ? saved.comment : "",
    cannotProvide: saved?.cannot_provide === true,
    appliesToFamily: saved?.applies_to_family === true,
  };
}

function answered(draft: Draft): boolean {
  return draft.cannotProvide || draft.value !== null || draft.comment.trim() !== "";
}

export function RequestPage() {
  const { assessmentId = "" } = useParams();
  const request = useRequest(assessmentId);
  if (request.isPending) return <Spinner />;
  if (!request.data) return <ErrorMessage error={request.error} />;
  return <RequestForm key={request.dataUpdatedAt} request={request.data} />;
}

/** Every open question needs a value, a comment or "cannot provide" before submitting (§19). */
function RequestForm({ request }: { request: SupplierRequest }) {
  const { session } = useSession();
  const queries = useQueryClient();
  const open = request.questions.filter((q) => q.status === "SENT");
  const closed = request.questions.filter((q) => q.status !== "SENT");
  const [drafts, setDrafts] = useState<Record<string, Draft>>(() =>
    Object.fromEntries(open.map((q) => [q.id, initial(q)])),
  );
  const refresh = () => queries.invalidateQueries({ queryKey: ["requests"] });
  const path = { params: { path: { assessment_id: request.assessment_id } } };

  const save = useMutation({
    mutationFn: () =>
      session.call((hub) =>
        hub.PUT("/api/v1/supplier/requests/{assessment_id}/answers", {
          ...path,
          body: {
            answers: open
              .filter((q) => answered(drafts[q.id] ?? initial(q)))
              .map((q) => {
                const draft = drafts[q.id] ?? initial(q);
                return {
                  question_id: q.id,
                  value: draft.cannotProvide ? null : draft.value,
                  comment: draft.comment.trim() || null,
                  cannot_provide: draft.cannotProvide,
                  applies_to_family: draft.appliesToFamily,
                };
              }),
          },
        }),
      ),
  });
  const submit = useMutation({
    mutationFn: async () => {
      await save.mutateAsync();
      return session.call((hub) =>
        hub.POST("/api/v1/supplier/requests/{assessment_id}/submit", path),
      );
    },
    onSuccess: refresh,
  });
  const simulate = useMutation({
    mutationFn: () =>
      session.call((hub) =>
        hub.POST("/api/v1/dev/assessments/{assessment_id}/simulate-supplier", path),
      ),
    onSuccess: refresh,
  });

  return (
    <>
      <PageHeader title={request.variant_label}>
        <StatusBadge status={request.status} />
      </PageHeader>
      <p className="mb-4 text-sm text-neutral-600">
        {request.family} · {request.article_no} · asked by {request.hospital}
      </p>
      {open.length === 0 ? (
        <Notice>Nothing is waiting for an answer.</Notice>
      ) : (
        <Card className="space-y-5">
          {open.map((question) => (
            <QuestionRow
              key={question.id}
              question={question}
              draft={drafts[question.id] ?? initial(question)}
              onChange={(draft) => {
                setDrafts({ ...drafts, [question.id]: draft });
              }}
            />
          ))}
          <div className="flex flex-wrap items-center gap-2 border-t border-neutral-100 pt-4">
            <Button
              variant="secondary"
              disabled={save.isPending}
              onClick={() => {
                save.mutate();
              }}
            >
              Save draft
            </Button>
            <Button
              disabled={submit.isPending}
              onClick={() => {
                submit.mutate();
              }}
            >
              Submit answers
            </Button>
            {import.meta.env.DEV && (
              <Button
                variant="ghost"
                disabled={simulate.isPending}
                onClick={() => {
                  simulate.mutate();
                }}
              >
                Let the simulator answer (dev)
              </Button>
            )}
            {save.isSuccess && !submit.isPending && (
              <span className="text-xs text-neutral-500">Draft saved.</span>
            )}
          </div>
          <ErrorMessage error={submit.error ?? save.error ?? simulate.error} />
        </Card>
      )}
      {closed.length > 0 && (
        <Card className="mt-4">
          <h2 className="mb-2 text-sm font-semibold">Answered</h2>
          <ul className="space-y-2 text-sm">
            {closed.map((question) => (
              <li key={question.id}>
                <p>{question.text}</p>
                <SubmittedAnswer question={question} />
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}

function QuestionRow({
  question,
  draft,
  onChange,
}: {
  question: SupplierQuestion;
  draft: Draft;
  onChange: (draft: Draft) => void;
}) {
  return (
    <div className="space-y-2">
      <p className="text-sm font-medium">{question.text}</p>
      <div className="grid gap-3 md:grid-cols-[16rem_1fr]">
        <ValueInput
          label={question.text}
          expected={question.expected_answer as unknown as ExpectedAnswer}
          value={draft.value}
          disabled={draft.cannotProvide}
          onChange={(value) => {
            onChange({ ...draft, value });
          }}
        />
        <Textarea
          aria-label={`Comment on: ${question.text}`}
          placeholder="Comment (optional, or instead of a value)"
          className="min-h-9"
          value={draft.comment}
          onChange={(event) => {
            onChange({ ...draft, comment: event.target.value });
          }}
        />
      </div>
      <div className="flex flex-wrap gap-4">
        <Label className="flex items-center gap-2 font-normal">
          <input
            type="checkbox"
            checked={draft.appliesToFamily}
            onChange={(event) => {
              onChange({ ...draft, appliesToFamily: event.target.checked });
            }}
          />
          Applies to the whole product family
        </Label>
        <Label className="flex items-center gap-2 font-normal">
          <input
            type="checkbox"
            checked={draft.cannotProvide}
            onChange={(event) => {
              onChange({ ...draft, cannotProvide: event.target.checked });
            }}
          />
          We cannot provide this
        </Label>
      </div>
    </div>
  );
}

function SubmittedAnswer({ question }: { question: SupplierQuestion }) {
  const saved = question.draft;
  if (!saved) return <Badge>{question.status.toLowerCase()}</Badge>;
  if (saved.cannot_provide === true)
    return <span className="text-neutral-500">cannot provide</span>;
  return (
    <span className="text-neutral-700">
      <ValueView value={saved.value} />
      {typeof saved.comment === "string" && <span className="ml-2">“{saved.comment}”</span>}
    </span>
  );
}
