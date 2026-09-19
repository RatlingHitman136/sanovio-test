import {
  Button,
  Card,
  ErrorMessage,
  Label,
  Notice,
  PageHeader,
  Select,
  Spinner,
  StatusBadge,
  VerdictBadge,
} from "@sanovio/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { useArticle, type Article } from "../articles/queries";
import { useSession } from "../sessionContext";
import { sameTradeItem } from "../shared/gs1";
import { useLocalNames } from "../shared/names";
import { useTemplates } from "../shared/templates";
import { Actions, ResolveDialog } from "./Actions";
import { ComparisonCard, VerdictCard } from "./Comparison";
import { HistoryCard } from "./History";
import { PurchaserQuestions, SupplierQuestions } from "./Questions";
import { useAssessment, type AssessmentDetail } from "./queries";
import { useAction } from "./useAction";

export function AssessmentPage() {
  const { assessmentId = "" } = useParams();
  const assessment = useAssessment(assessmentId);
  const names = useLocalNames(assessment.data ? [assessment.data.article_ref] : []);
  const summary = assessment.data ? names.article(assessment.data.article_ref) : undefined;
  const article = useArticle(summary?.id ?? "");
  const templates = useTemplates();

  if (assessment.isPending) return <Spinner />;
  if (!assessment.data) return <ErrorMessage error={assessment.error} />;
  const detail = assessment.data;
  const round = detail.rounds.at(-1);
  const template = templates.data?.get(detail.template_code);
  const articleDetail = summary ? article.data : undefined;

  return (
    <>
      <PageHeader title={detail.variant_label}>
        <StatusBadge status={detail.status} />
        <VerdictBadge verdict={detail.final_verdict ?? detail.proposed_verdict} />
      </PageHeader>
      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <div className="text-sm text-neutral-600">
          {detail.supplier} · for{" "}
          {summary ? (
            <Link to={`/articles/${summary.id}`} className="text-accent hover:underline">
              {summary.name}
            </Link>
          ) : (
            detail.article_ref
          )}{" "}
          · round {detail.current_round}
          {detail.manual_reason && ` · ${detail.manual_reason.replaceAll("_", " ").toLowerCase()}`}
        </div>
        <div className="flex flex-wrap items-end gap-4">
          <Assignee assessment={detail} />
          <Actions assessment={detail} />
        </div>
      </div>
      {detail.status === "ASSESSING" && <Notice>The hub is assessing this round…</Notice>}
      {detail.status === "AWAITING_ANSWERS" && (
        <Notice>Waiting for {detail.supplier} to answer.</Notice>
      )}
      <IdentifierBanner assessment={detail} article={articleDetail} />
      <div className="mt-4 grid gap-4 xl:grid-cols-[2fr_1fr]">
        <div className="space-y-4">
          <PurchaserQuestions assessment={detail} article={articleDetail} />
          {round && <ComparisonCard round={round} article={articleDetail} template={template} />}
        </div>
        <div className="space-y-4">
          {round && <VerdictCard round={round} />}
          <SupplierQuestions assessment={detail} />
          <HistoryCard assessment={detail} />
          {detail.resolution_kind && (
            <Card className="text-sm">
              Resolved ({detail.resolution_kind.toLowerCase()}) by{" "}
              {names.person(detail.resolved_by_subject_id)}
              {detail.resolution_note && <p className="mt-1">“{detail.resolution_note}”</p>}
            </Card>
          )}
        </div>
      </div>
    </>
  );
}

function Assignee({ assessment }: { assessment: AssessmentDetail }) {
  const { session } = useSession();
  const names = useLocalNames([]);
  const assign = useAction(assessment.id, (subjectId: string) =>
    session.atHub((hub) =>
      hub.PUT("/api/v1/assessments/{assessment_id}/assignee", {
        params: { path: { assessment_id: assessment.id } },
        body: { subject_id: subjectId },
      }),
    ),
  );
  return (
    <div>
      <Label htmlFor="assignee" className="text-xs">
        Assigned to
      </Label>
      <Select
        id="assignee"
        className="w-48"
        value={assessment.assigned_to_subject_id ?? ""}
        disabled={assign.isPending}
        onChange={(event) => {
          assign.mutate(event.target.value);
        }}
      >
        <option value="" disabled>
          nobody
        </option>
        {names.users
          .filter((user) => user.is_active && user.role === "PURCHASER")
          .map((user) => (
            <option key={user.hub_subject_id} value={user.hub_subject_id}>
              {user.display_name}
            </option>
          ))}
      </Select>
      <ErrorMessage error={assign.error} />
    </div>
  );
}

/**
 * With product hints off only the browser holds both sides' GTINs (D51). A valid match means
 * this is the product the hospital already buys, whatever the attributes say.
 */
function IdentifierBanner({
  assessment,
  article,
}: {
  assessment: AssessmentDetail;
  article: Article | undefined;
}) {
  const { session } = useSession();
  const [resolving, setResolving] = useState(false);
  const variant = useQuery({
    queryKey: ["hub", "variant", assessment.variant_id],
    queryFn: () =>
      session.atHub((hub) =>
        hub.GET("/api/v1/catalog/variants/{variant_id}/attributes", {
          params: { path: { variant_id: assessment.variant_id } },
        }),
      ),
    staleTime: 60_000,
  });
  const theirs = (variant.data?.identifiers ?? []) as { scheme: string; value: string }[];
  const gtin = article ? sameTradeItem(article.identifiers, theirs) : undefined;
  if (!gtin) return null;
  const open = !["RESOLVED", "CANCELLED", "ASSESSING"].includes(assessment.status);
  return (
    <Card className="mt-4 border-green-200 bg-green-50 text-sm">
      Same trade item: GTIN {gtin} is on both your article and this product. This is the product you
      already buy.
      {open && (
        <Button
          size="sm"
          className="ml-3"
          onClick={() => {
            setResolving(true);
          }}
        >
          Resolve as equivalent
        </Button>
      )}
      {resolving && (
        <ResolveDialog
          assessment={assessment}
          mode={assessment.status === "PROPOSED_RESOLUTION" ? "override" : "manual"}
          presetVerdict="EQUIVALENT"
          presetNote={`Same trade item: GTIN ${gtin} on both sides.`}
          onClose={() => {
            setResolving(false);
          }}
        />
      )}
    </Card>
  );
}
