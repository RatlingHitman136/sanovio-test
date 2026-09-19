import { Badge, Card, Empty, Input, PageHeader, Spinner, Table, Td, Th } from "@sanovio/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router";

import { useSession } from "../sessionContext";

export function ArticlesPage() {
  const { session } = useSession();
  const [text, setText] = useState("");
  const articles = useQuery({
    queryKey: ["node", "articles", text],
    queryFn: () =>
      session.atNode((node) =>
        node.GET("/api/v1/articles", { params: { query: text ? { q: text } : {} } }),
      ),
  });

  return (
    <>
      <PageHeader title="Articles">
        <Input
          aria-label="Filter articles"
          placeholder="Name or internal ID"
          className="w-64"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
          }}
        />
      </PageHeader>
      <Card>
        {articles.isPending ? (
          <Spinner />
        ) : !articles.data?.length ? (
          <Empty>No articles.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>ID</Th>
                <Th>Article</Th>
                <Th>Category</Th>
                <Th>Data quality</Th>
              </tr>
            </thead>
            <tbody>
              {articles.data.map((article) => (
                <tr key={article.id}>
                  <Td className="text-neutral-500">{article.internal_id}</Td>
                  <Td>
                    <Link to={`/articles/${article.id}`} className="text-accent hover:underline">
                      {article.name}
                    </Link>
                    {article.brand && (
                      <span className="ml-2 text-xs text-neutral-500">{article.brand}</span>
                    )}
                  </Td>
                  <Td>{article.category_code ?? "–"}</Td>
                  <Td className="space-x-1">
                    {article.data_quality_issues.map((issue) => (
                      <Badge key={issue} tone="warn">
                        {issue}
                      </Badge>
                    ))}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
