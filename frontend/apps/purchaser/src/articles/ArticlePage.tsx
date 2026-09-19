import {
  Badge,
  Button,
  Card,
  CardTitle,
  ErrorMessage,
  Label,
  PageHeader,
  Select,
  Spinner,
  Table,
  Td,
  Th,
  ValueView,
} from "@sanovio/ui";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "react-router";

import { useArticle, type Article } from "./queries";
import { useSession } from "../sessionContext";
import { labelFor, useTemplates } from "../shared/templates";
import { FactDialog } from "./FactDialog";
import { SearchCard } from "./SearchCard";

export function ArticlePage() {
  const { articleId = "" } = useParams();
  const article = useArticle(articleId);
  const templates = useTemplates();

  if (article.isPending || templates.isPending) return <Spinner />;
  if (!article.data) return <ErrorMessage error={article.error} />;
  const template = templates.data?.get(article.data.category_code ?? "");
  return (
    <>
      <PageHeader title={article.data.name}>
        {article.data.data_quality_issues.map((issue) => (
          <Badge key={issue} tone="warn">
            {issue}
          </Badge>
        ))}
      </PageHeader>
      <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
        <div className="space-y-4">
          <SearchCard article={article.data} />
          <FactsCard article={article.data} labels={(key) => labelFor(template, key)} />
        </div>
        <div className="space-y-4">
          <CategoryCard article={article.data} codes={[...(templates.data?.keys() ?? [])]} />
          <CurrentProductCard article={article.data} />
          <LocalDataCard article={article.data} />
        </div>
      </div>
    </>
  );
}

function FactsCard({ article, labels }: { article: Article; labels: (key: string) => string }) {
  const [editing, setEditing] = useState<string | null>(null);
  return (
    <Card>
      <CardTitle>Attributes</CardTitle>
      <Table>
        <thead>
          <tr>
            <Th>Attribute</Th>
            <Th>Value</Th>
            <Th>Source</Th>
            <Th />
          </tr>
        </thead>
        <tbody>
          {article.attributes.map((fact) => (
            <tr key={fact.key}>
              <Td>{labels(fact.key)}</Td>
              <Td>
                <ValueView value={fact.value} />
                {fact.quote && <div className="text-xs text-neutral-500">“{fact.quote}”</div>}
              </Td>
              <Td className="text-xs text-neutral-500">{fact.source}</Td>
              <Td className="text-right">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setEditing(fact.key);
                  }}
                >
                  Correct
                </Button>
              </Td>
            </tr>
          ))}
          {[...article.unknown_attributes, ...article.unavailable_attributes].map((key) => (
            <tr key={key} className="text-neutral-500">
              <Td>{labels(key)}</Td>
              <Td>
                <Badge tone={article.unavailable_attributes.includes(key) ? "neutral" : "info"}>
                  {article.unavailable_attributes.includes(key) ? "cannot provide" : "unknown"}
                </Badge>
              </Td>
              <Td />
              <Td className="text-right">
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => {
                    setEditing(key);
                  }}
                >
                  Enter
                </Button>
              </Td>
            </tr>
          ))}
        </tbody>
      </Table>
      {editing && (
        <FactDialog
          article={article}
          attributeKey={editing}
          onClose={() => {
            setEditing(null);
          }}
        />
      )}
    </Card>
  );
}

function CategoryCard({ article, codes }: { article: Article; codes: string[] }) {
  const { session } = useSession();
  const queries = useQueryClient();
  const change = useMutation({
    mutationFn: (code: string) =>
      session.atNode((node) =>
        node.PUT("/api/v1/articles/{article_id}/category", {
          params: { path: { article_id: article.id } },
          body: { category_code: code },
        }),
      ),
    onSuccess: () => queries.invalidateQueries({ queryKey: ["node"] }),
  });
  return (
    <Card>
      <CardTitle>Category</CardTitle>
      <Label htmlFor="category">Template</Label>
      <Select
        id="category"
        value={article.category_code ?? ""}
        disabled={change.isPending}
        onChange={(event) => {
          change.mutate(event.target.value);
        }}
      >
        {codes.map((code) => (
          <option key={code}>{code}</option>
        ))}
      </Select>
      <p className="mt-1 text-xs text-neutral-500">Set by {article.category_source ?? "–"}</p>
      <ErrorMessage error={change.error} />
    </Card>
  );
}

function CurrentProductCard({ article }: { article: Article }) {
  const { session } = useSession();
  const queries = useQueryClient();
  const remove = useMutation({
    mutationFn: () =>
      session.atNode((node) =>
        node.DELETE("/api/v1/articles/{article_id}/reference", {
          params: { path: { article_id: article.id } },
        }),
      ),
    onSuccess: () => queries.invalidateQueries({ queryKey: ["node"] }),
  });
  return (
    <Card>
      <CardTitle>Current product</CardTitle>
      {article.reference ? (
        <>
          <p className="text-sm">{article.reference.label ?? article.reference.variant_id}</p>
          <Button
            className="mt-2"
            size="sm"
            variant="secondary"
            disabled={remove.isPending}
            onClick={() => {
              remove.mutate();
            }}
          >
            Remove
          </Button>
        </>
      ) : (
        <p className="text-sm text-neutral-500">
          None. Mark a search result as the product you buy today to fill in what the name does not
          say.
        </p>
      )}
      <ErrorMessage error={remove.error} />
    </Card>
  );
}

function LocalDataCard({ article }: { article: Article }) {
  const rows: [string, string | number | null][] = [
    ["Internal ID", article.internal_id],
    ["Brand", article.brand],
    ["Order unit", article.order_unit],
    ["Units per order unit", article.base_units_per_order_unit],
    [
      "Target price",
      article.target_net_price && `${article.target_net_price} ${article.currency ?? ""}`,
    ],
    ["Annual quantity", article.annual_quantity],
  ];
  return (
    <Card>
      <CardTitle>Hospital data</CardTitle>
      <p className="mb-2 text-xs text-neutral-500">Stays in the hospital; never sent to the hub.</p>
      <dl className="grid grid-cols-2 gap-y-1 text-sm">
        {rows.map(([name, value]) => (
          <div key={name} className="contents">
            <dt className="text-neutral-500">{name}</dt>
            <dd>{value ?? "–"}</dd>
          </div>
        ))}
      </dl>
      {article.identifiers.length > 0 && (
        <ul className="mt-3 space-y-1 text-sm">
          {article.identifiers.map((identifier) => (
            <li key={`${identifier.scheme}-${identifier.value}`}>
              <span className="font-mono">
                {identifier.scheme} {identifier.value}
              </span>{" "}
              {identifier.checksum_valid === false && <Badge tone="warn">check digit fails</Badge>}
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
