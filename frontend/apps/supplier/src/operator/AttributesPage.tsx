import { Badge, Card, Empty, PageHeader, Select, Spinner, Table, Td, Th } from "@sanovio/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { useSession } from "../sessionContext";

const TONE = { APPROVED: "good", PROVISIONAL: "warn", DEPRECATED: "neutral" } as const;

/** The shared registry: what each attribute is, independent of any category (§7.2). */
export function AttributesPage() {
  const { session } = useSession();
  const [status, setStatus] = useState("");
  const attributes = useQuery({
    queryKey: ["admin", "attributes", status],
    queryFn: () =>
      session.call((hub) =>
        hub.GET("/api/v1/attributes", { params: { query: status ? { status } : {} } }),
      ),
  });
  return (
    <>
      <PageHeader title="Attributes">
        <Select
          aria-label="Status"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value);
          }}
        >
          <option value="">every status</option>
          <option value="APPROVED">approved</option>
          <option value="PROVISIONAL">provisional</option>
          <option value="DEPRECATED">deprecated</option>
        </Select>
      </PageHeader>
      <Card>
        {attributes.isPending ? (
          <Spinner />
        ) : !attributes.data?.length ? (
          <Empty>No attributes.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Key</Th>
                <Th>Label</Th>
                <Th>Type</Th>
                <Th>Options</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {attributes.data.map((attribute) => (
                <tr key={attribute.key}>
                  <Td className="font-mono text-xs">{attribute.key}</Td>
                  <Td>{(attribute.labels as { en?: string }).en}</Td>
                  <Td className="text-xs">
                    {attribute.kind === "IDENTIFIER" ? "identifier" : attribute.value_type}
                    {attribute.unit ? ` (${attribute.unit})` : ""}
                  </Td>
                  <Td className="text-xs text-neutral-600">{attribute.options?.join(", ")}</Td>
                  <Td>
                    <Badge tone={TONE[attribute.status as keyof typeof TONE]}>
                      {attribute.status.toLowerCase()}
                    </Badge>
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
