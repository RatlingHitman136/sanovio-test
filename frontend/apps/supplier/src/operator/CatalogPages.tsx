import {
  Badge,
  Button,
  Card,
  ErrorMessage,
  Notice,
  PageHeader,
  Spinner,
  Table,
  Td,
  Th,
} from "@sanovio/ui";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";

import { FamilyValues } from "../catalog/FamilyPage";
import { useSession } from "../sessionContext";

/** Every supplier's catalog, read only: the values belong to the supplier (§17.1). */
export function OperatorCatalogPage() {
  const { session } = useSession();
  const families = useQuery({
    queryKey: ["admin", "families"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/admin/catalog/families")),
  });
  if (families.isPending) return <Spinner />;
  return (
    <>
      <PageHeader title="Catalogs" />
      <Card>
        <Table>
          <thead>
            <tr>
              <Th>Family</Th>
              <Th>Supplier</Th>
              <Th>Category</Th>
              <Th>Variants</Th>
              <Th>Catalog text</Th>
            </tr>
          </thead>
          <tbody>
            {(families.data ?? []).map((family) => (
              <tr key={family.id}>
                <Td>
                  <Link to={`/catalog/${family.id}`} className="text-accent hover:underline">
                    {family.name}
                  </Link>
                </Td>
                <Td>{family.supplier}</Td>
                <Td className="text-xs">{family.category_code ?? "uncategorised"}</Td>
                <Td>{family.variants}</Td>
                <Td>
                  {family.normalized ? (
                    <Badge tone="good">read</Badge>
                  ) : (
                    <Badge tone="warn">changed since read</Badge>
                  )}
                </Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </>
  );
}

export function OperatorFamilyPage() {
  const { familyId = "" } = useParams();
  const { session } = useSession();
  const path = { params: { path: { family_id: familyId } } };
  const family = useQuery({
    queryKey: ["admin", "family", familyId],
    queryFn: () =>
      session.call((hub) => hub.GET("/api/v1/admin/catalog/families/{family_id}", path)),
  });
  const reread = useMutation({
    mutationFn: () =>
      session.call((hub) => hub.POST("/api/v1/admin/catalog/families/{family_id}/normalize", path)),
  });
  if (family.isPending) return <Spinner />;
  if (!family.data) return <ErrorMessage error={family.error} />;
  return (
    <>
      <PageHeader title={family.data.name}>
        <Button
          variant="secondary"
          disabled={reread.isPending || reread.isSuccess}
          onClick={() => {
            reread.mutate();
          }}
        >
          Re-read catalog data
        </Button>
      </PageHeader>
      {reread.isSuccess && (
        <Notice>Queued: the reading fills attributes that are still missing.</Notice>
      )}
      <ErrorMessage error={reread.error} />
      <FamilyValues detail={family.data} readOnly />
    </>
  );
}
