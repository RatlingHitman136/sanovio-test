import {
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
import { useQuery } from "@tanstack/react-query";

import { useSession } from "../sessionContext";

/** Our own families and variants with the values the hub holds, including answered ones. */
export function CatalogPage() {
  const { session } = useSession();
  const catalog = useQuery({
    queryKey: ["catalog"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/supplier/catalog")),
  });
  if (catalog.isPending) return <Spinner />;
  return (
    <>
      <PageHeader title="Catalog" />
      {!catalog.data?.length ? (
        <Empty>No products.</Empty>
      ) : (
        <div className="space-y-4">
          {catalog.data.map((family) => (
            <Card key={family.id}>
              <CardTitle>{family.name}</CardTitle>
              <p className="mb-3 text-xs text-neutral-500">
                {family.category_code ?? "uncategorised"}
                {family.source_document &&
                  ` · ${family.source_document}${family.source_page ? `, p. ${family.source_page}` : ""}`}
              </p>
              <Table>
                <thead>
                  <tr>
                    <Th>Article</Th>
                    <Th>Values</Th>
                  </tr>
                </thead>
                <tbody>
                  {family.variants.map((variant) => (
                    <tr key={variant.variant_id}>
                      <Td className="whitespace-nowrap">{variant.display_name}</Td>
                      <Td className="text-xs text-neutral-600">
                        {Object.entries(variant.attributes)
                          .map(([key, value]) => `${key}: ${formatValue(value)}`)
                          .join(" · ")}
                      </Td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            </Card>
          ))}
        </div>
      )}
    </>
  );
}
