import type { HubSchemas, PurchaserSession } from "@sanovio/api";

export type Requirement = HubSchemas["schemas"]["RequirementPayload"];

/**
 * A fresh requirement from the node (§16). The node's and the hub's generated types describe
 * the same payload; the hub re-validates it on arrival either way.
 */
export async function issueRequirement(
  session: PurchaserSession,
  articleId: string,
  answeredQuestionIds: string[] = [],
): Promise<Requirement> {
  const issued = await session.atNode((node) =>
    node.POST("/api/v1/articles/{article_id}/requirement", {
      params: { path: { article_id: articleId } },
      body: { answered_question_ids: answeredQuestionIds },
    }),
  );
  return issued.requirement;
}
