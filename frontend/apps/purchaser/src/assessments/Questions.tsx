import { ApiError } from "@sanovio/api";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  Empty,
  ErrorMessage,
  Label,
  Notice,
  Textarea,
  ValueInput,
  ValueView,
  type ExpectedAnswer,
  type TypedValue,
} from "@sanovio/ui";
import { useState } from "react";

import type { Article } from "../articles/queries";
import { useSession } from "../sessionContext";
import { issueRequirement } from "../shared/requirements";
import type { AssessmentDetail, Question } from "./queries";
import { useAction } from "./useAction";

const OPEN = new Set(["DRAFT", "SENT"]);

function inReview(assessment: AssessmentDetail): boolean {
  return assessment.status === "NEEDS_QUESTION_REVIEW";
}

/** Questions for the supplier: edited, withdrawn or added during review, then sent (§11). */
export function SupplierQuestions({ assessment }: { assessment: AssessmentDetail }) {
  const { session } = useSession();
  const questions = assessment.questions.filter((q) => q.addressee === "SUPPLIER");
  const [draft, setDraft] = useState("");
  const add = useAction(assessment.id, (text: string) =>
    session.atHub((hub) =>
      hub.POST("/api/v1/assessments/{assessment_id}/questions", {
        params: { path: { assessment_id: assessment.id } },
        body: { version: assessment.version, addressee: "SUPPLIER", attribute_key: null, text },
      }),
    ),
  );
  const send = useAction(assessment.id, () =>
    session.atHub((hub) =>
      hub.POST("/api/v1/assessments/{assessment_id}/send-questions", {
        params: { path: { assessment_id: assessment.id } },
        body: { version: assessment.version },
      }),
    ),
  );
  const purchaserOwes = assessment.questions.some(
    (q) => q.addressee === "PURCHASER" && OPEN.has(q.status),
  );
  const pending =
    send.error instanceof ApiError && send.error.code === "ATTRIBUTE_PROPOSAL_PENDING";

  return (
    <Card>
      <CardTitle>Questions to {assessment.supplier}</CardTitle>
      {questions.length === 0 ? (
        <Empty>No questions for the supplier.</Empty>
      ) : (
        <ul className="divide-y divide-neutral-100">
          {questions.map((question) => (
            <SupplierQuestion key={question.id} assessment={assessment} question={question} />
          ))}
        </ul>
      )}
      {inReview(assessment) && (
        <div className="mt-4 space-y-3 border-t border-neutral-100 pt-4">
          <Label htmlFor="new-question">Ask something the template does not cover</Label>
          <Textarea
            id="new-question"
            value={draft}
            onChange={(event) => {
              setDraft(event.target.value);
            }}
          />
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              size="sm"
              disabled={!draft.trim() || add.isPending}
              onClick={() => {
                add.mutate(draft.trim(), {
                  onSuccess: () => {
                    setDraft("");
                  },
                });
              }}
            >
              Add question
            </Button>
            <Button
              size="sm"
              disabled={purchaserOwes || send.isPending}
              onClick={() => {
                send.mutate(undefined);
              }}
            >
              Send questions
            </Button>
            {purchaserOwes && (
              <span className="text-xs text-neutral-500">
                Answer or withdraw your questions first.
              </span>
            )}
          </div>
          {pending ? (
            <Notice>
              New questions are still being matched to attributes; send again in a few seconds.
            </Notice>
          ) : (
            <ErrorMessage error={add.error ?? send.error} />
          )}
        </div>
      )}
    </Card>
  );
}

function SupplierQuestion({
  assessment,
  question,
}: {
  assessment: AssessmentDetail;
  question: Question;
}) {
  const { session } = useSession();
  const [text, setText] = useState<string | null>(null);
  const edit = useAction(assessment.id, (body: { text?: string; withdraw?: boolean }) =>
    session.atHub((hub) =>
      hub.PATCH("/api/v1/assessments/{assessment_id}/questions/{question_id}", {
        params: { path: { assessment_id: assessment.id, question_id: question.id } },
        body: { version: assessment.version, withdraw: false, ...body },
      }),
    ),
  );
  const editable = inReview(assessment) && question.status === "DRAFT";
  return (
    <li className="py-2 text-sm">
      <div className="flex items-start justify-between gap-3">
        {text === null ? (
          <p className={question.status === "WITHDRAWN" ? "text-neutral-400 line-through" : ""}>
            {question.text}
          </p>
        ) : (
          <Textarea
            aria-label="Question text"
            value={text}
            onChange={(event) => {
              setText(event.target.value);
            }}
          />
        )}
        <Badge tone={question.status === "ANSWERED" ? "good" : "neutral"}>
          {question.status.toLowerCase()}
        </Badge>
      </div>
      {question.attribute_key && (
        <div className="text-xs text-neutral-500">{question.attribute_key}</div>
      )}
      {question.answer && <AnswerView answer={question.answer} />}
      {editable && (
        <div className="mt-1 flex gap-2">
          {text === null ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                setText(question.text);
              }}
            >
              Edit
            </Button>
          ) : (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => {
                edit.mutate(
                  { text },
                  {
                    onSuccess: () => {
                      setText(null);
                    },
                  },
                );
              }}
            >
              Save
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => {
              edit.mutate({ withdraw: true });
            }}
          >
            Withdraw
          </Button>
        </div>
      )}
      <ErrorMessage error={edit.error} />
    </li>
  );
}

function AnswerView({ answer }: { answer: Record<string, unknown> }) {
  return (
    <div className="mt-1 rounded bg-neutral-50 px-2 py-1 text-xs text-neutral-700">
      {answer.cannot_provide ? (
        "The supplier cannot provide this."
      ) : (
        <>
          {answer.value !== null && <ValueView value={answer.value} />}
          {typeof answer.comment === "string" && <span className="ml-2">“{answer.comment}”</span>}
          {answer.applies_to_family === true && <span className="ml-2">(whole family)</span>}
        </>
      )}
    </div>
  );
}

interface Draft {
  value: TypedValue | null;
  cannotProvide: boolean;
}

/**
 * Questions for us, answered at the node and forwarded as a new requirement (§11): the hub
 * never sees an answer by any other way.
 */
export function PurchaserQuestions({
  assessment,
  article,
}: {
  assessment: AssessmentDetail;
  article: Article | undefined;
}) {
  const { session } = useSession();
  const open = assessment.questions.filter(
    (q) => q.addressee === "PURCHASER" && OPEN.has(q.status),
  );
  const [drafts, setDrafts] = useState<Record<string, Draft>>({});
  const answered = open.filter((q) => {
    const draft = drafts[q.id];
    return draft && (draft.cannotProvide || draft.value !== null);
  });
  const submit = useAction(assessment.id, async () => {
    if (!article) throw new Error("the article is not loaded yet");
    for (const question of answered) {
      const draft = drafts[question.id] ?? { value: null, cannotProvide: false };
      await session.atNode((node) =>
        node.PUT("/api/v1/articles/{article_id}/facts/{attribute_key}", {
          params: {
            path: { article_id: article.id, attribute_key: question.attribute_key ?? "" },
          },
          body: {
            cannot_provide: draft.cannotProvide,
            value: draft.cannotProvide ? null : (draft.value as never),
            hub_question_id: question.id,
          },
        }),
      );
    }
    const requirement = await issueRequirement(
      session,
      article.id,
      answered.map((q) => q.id),
    );
    return session.atHub((hub) =>
      hub.POST("/api/v1/assessments/{assessment_id}/requirements", {
        params: { path: { assessment_id: assessment.id } },
        body: { requirement, version: assessment.version },
      }),
    );
  });
  const withdraw = useAction(assessment.id, (questionId: string) =>
    session.atHub((hub) =>
      hub.PATCH("/api/v1/assessments/{assessment_id}/questions/{question_id}", {
        params: { path: { assessment_id: assessment.id, question_id: questionId } },
        body: { version: assessment.version, withdraw: true },
      }),
    ),
  );

  if (open.length === 0) return null;
  return (
    <Card className="border-amber-200">
      <CardTitle>Questions for you</CardTitle>
      <p className="mb-3 text-xs text-neutral-500">
        Answers are saved at your node; only the new requirement goes to the hub.
      </p>
      <ul className="space-y-3">
        {open.map((question) => {
          const draft = drafts[question.id] ?? { value: null, cannotProvide: false };
          const change = (next: Partial<Draft>) => {
            setDrafts({ ...drafts, [question.id]: { ...draft, ...next } });
          };
          return (
            <li
              key={question.id}
              className="text-sm"
              data-attribute-key={question.attribute_key ?? ""}
            >
              <p className="mb-1">{question.text}</p>
              <div className="flex flex-wrap items-center gap-3">
                <div className="w-64">
                  <ValueInput
                    label={question.text}
                    expected={question.expected_answer as unknown as ExpectedAnswer}
                    value={draft.value}
                    disabled={draft.cannotProvide}
                    onChange={(value) => {
                      change({ value });
                    }}
                  />
                </div>
                <Label className="flex items-center gap-2 font-normal">
                  <input
                    type="checkbox"
                    checked={draft.cannotProvide}
                    onChange={(event) => {
                      change({ cannotProvide: event.target.checked });
                    }}
                  />
                  We cannot provide this
                </Label>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    withdraw.mutate(question.id);
                  }}
                >
                  Withdraw
                </Button>
              </div>
            </li>
          );
        })}
      </ul>
      <Button
        className="mt-4"
        size="sm"
        disabled={answered.length === 0 || submit.isPending}
        onClick={() => {
          submit.mutate(undefined, {
            onSuccess: () => {
              setDrafts({});
            },
          });
        }}
      >
        Save {answered.length || ""} answer{answered.length === 1 ? "" : "s"}
      </Button>
      <ErrorMessage error={submit.error ?? withdraw.error} />
    </Card>
  );
}
