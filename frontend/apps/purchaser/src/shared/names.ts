import { useQuery } from "@tanstack/react-query";

import { useSession } from "../sessionContext";

/**
 * Names the hub must never know, joined in the browser (§14): article names by `article_ref`
 * and colleagues by their pseudonymous subject id.
 */
export function useLocalNames(articleRefs: string[]) {
  const { session } = useSession();
  const refs = [...new Set(articleRefs)].sort();
  const articles = useQuery({
    queryKey: ["node", "articles", "by-ref", refs],
    enabled: refs.length > 0,
    queryFn: () =>
      session.atNode((node) =>
        node.GET("/api/v1/articles", { params: { query: { article_ref: refs.join(",") } } }),
      ),
  });
  const users = useQuery({
    queryKey: ["node", "users"],
    queryFn: () => session.atNode((node) => node.GET("/api/v1/users")),
    staleTime: 60_000,
  });
  const byRef = new Map((articles.data ?? []).map((article) => [article.article_ref, article]));
  const bySubject = new Map((users.data ?? []).map((user) => [user.hub_subject_id, user]));
  return {
    article: (ref: string) => byRef.get(ref),
    person: (subject: string | null | undefined) =>
      subject ? (bySubject.get(subject)?.display_name ?? "someone else") : "–",
    users: users.data ?? [],
  };
}
