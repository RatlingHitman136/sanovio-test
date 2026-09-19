import type { NodeSchemas } from "@sanovio/api";
import { useQuery } from "@tanstack/react-query";

import { useSession } from "../sessionContext";

export type Article = NodeSchemas["schemas"]["ArticleDetail"];

export function useArticle(articleId: string) {
  const { session } = useSession();
  return useQuery({
    queryKey: ["node", "article", articleId],
    queryFn: () =>
      session.atNode((node) =>
        node.GET("/api/v1/articles/{article_id}", {
          params: { path: { article_id: articleId } },
        }),
      ),
  });
}
