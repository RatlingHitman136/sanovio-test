import {
  Badge,
  Button,
  Card,
  CardTitle,
  Empty,
  PageHeader,
  Spinner,
  Table,
  Td,
  Th,
  formatValue,
} from "@sanovio/ui";
import type { HubSchemas } from "@sanovio/api";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate } from "react-router";

import { useSession } from "../sessionContext";
import { FamilyDialog } from "./FamilyForms";
import { useFamilySaved } from "./useFamilySaved";

type Family = HubSchemas["schemas"]["SupplierFamilyRow"];

function gapsOf(family: Family): number {
  return family.variants.reduce(
    (sum, row) => sum + Object.values(row.gaps).reduce((a, b) => a + b, 0),
    0,
  );
}

/** Each family as its size table: per article only what tells the variants apart, its pack,
 * and how many answers are still missing (the family page has the shared values). */
export function CatalogPage() {
  const { session, me } = useSession();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const created = useFamilySaved(() => {
    setCreating(false);
  });
  const catalog = useQuery({
    queryKey: ["catalog"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/supplier/catalog")),
  });
  if (catalog.isPending) return <Spinner />;
  return (
    <>
      <PageHeader title="Catalog">
        <Button
          onClick={() => {
            setCreating(true);
          }}
        >
          New family
        </Button>
      </PageHeader>
      {creating && (
        <FamilyDialog
          manufacturer={me.organization}
          onSaved={(family) => {
            created(family);
            void navigate(`/catalog/${family.id}`);
          }}
          onClose={() => {
            setCreating(false);
          }}
        />
      )}
      {!catalog.data?.length ? (
        <Empty>No products.</Empty>
      ) : (
        <div className="space-y-4">
          {catalog.data.map((family) => {
            const gaps = gapsOf(family);
            return (
              <Card key={family.id}>
                <CardTitle>
                  <Link to={`/catalog/${family.id}`} className="text-accent hover:underline">
                    {family.name}
                  </Link>
                </CardTitle>
                <p className="mb-3 flex flex-wrap items-center gap-2 text-xs text-neutral-500">
                  <span>{family.category_code ?? "uncategorised"}</span>
                  <span>·</span>
                  <span>
                    {family.variants.length} {family.variants.length === 1 ? "article" : "articles"}
                  </span>
                  {gaps > 0 && (
                    <>
                      <span>·</span>
                      <Link to={`/catalog/${family.id}`} className="hover:underline">
                        <Badge tone="warn">{`${gaps} to fill in`}</Badge>
                      </Link>
                    </>
                  )}
                  {family.reading && <Badge tone="info">being read</Badge>}
                </p>
                <Table>
                  <thead>
                    <tr>
                      <Th>Article</Th>
                      <Th>Label</Th>
                      {family.columns.map((column) => (
                        <Th key={column.key}>
                          {column.label}
                          {column.unit ? ` (${column.unit})` : ""}
                        </Th>
                      ))}
                      <Th>Pack</Th>
                      <Th>Missing</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {family.variants.map((row) => (
                      <tr key={row.variant_id} className={row.is_active ? undefined : "opacity-50"}>
                        <Td className="whitespace-nowrap">
                          {row.article_no}
                          {!row.is_active && <> · retired</>}
                        </Td>
                        <Td>{row.label}</Td>
                        {family.columns.map((column) => (
                          <Td key={column.key} className="whitespace-nowrap">
                            {row.values[column.key]
                              ? formatValue(row.values[column.key]?.value)
                              : "–"}
                          </Td>
                        ))}
                        <Td className="whitespace-nowrap text-xs text-neutral-600">
                          {row.units_per_order_unit
                            ? `${row.units_per_order_unit}${row.order_unit ? ` / ${row.order_unit}` : ""}`
                            : (row.order_unit ?? "–")}
                        </Td>
                        <Td className="space-x-1 whitespace-nowrap">
                          {Object.entries(row.gaps).length === 0
                            ? "–"
                            : Object.entries(row.gaps).map(([criticality, count]) => (
                                <Badge
                                  key={criticality}
                                  tone={criticality === "critical" ? "bad" : "warn"}
                                >
                                  {`${count} ${criticality}`}
                                </Badge>
                              ))}
                        </Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </Card>
            );
          })}
        </div>
      )}
    </>
  );
}
