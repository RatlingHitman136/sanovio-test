import type { HubSchemas } from "@sanovio/api";
import { Card, Empty, PageHeader, Select, Spinner, Table, Td, Th } from "@sanovio/ui";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { useSession } from "../sessionContext";
import { when } from "./shared";

type Action = HubSchemas["schemas"]["AuditAction"];

const ACTIONS: Action[] = [
  "TENANT_CREATED",
  "SIGNING_KEY_REGISTERED",
  "SIGNING_KEY_REVOKED",
  "PRINCIPAL_BLOCKED",
  "PRINCIPAL_UNBLOCKED",
  "PROPOSAL_APPROVED",
  "PROPOSAL_MERGED",
  "PROPOSAL_REJECTED",
  "TEMPLATE_EDITED",
  "SUPPLIER_CREATED",
  "USER_CREATED",
  "USER_DEACTIVATED",
  "USER_REACTIVATED",
  "PASSWORD_RESET",
  "FAMILY_RENORMALIZED",
  "JOB_RETRIED",
];

/** Every change an operator made at the hub, newest first (H.23). */
export function AuditPage() {
  const { session } = useSession();
  const [action, setAction] = useState<Action | "">("");
  const audit = useQuery({
    queryKey: ["admin", "audit", action],
    queryFn: () =>
      session.call((hub) =>
        hub.GET("/api/v1/admin/audit", { params: { query: action ? { action } : {} } }),
      ),
  });
  return (
    <>
      <PageHeader title="Audit">
        <Select
          aria-label="Action"
          value={action}
          onChange={(event) => {
            setAction(event.target.value as Action | "");
          }}
        >
          <option value="">every action</option>
          {ACTIONS.map((value) => (
            <option key={value} value={value}>
              {value.replaceAll("_", " ").toLowerCase()}
            </option>
          ))}
        </Select>
      </PageHeader>
      <Card>
        {audit.isPending ? (
          <Spinner />
        ) : !audit.data?.length ? (
          <Empty>Nothing yet.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>When</Th>
                <Th>Operator</Th>
                <Th>Action</Th>
                <Th>Target</Th>
                <Th>Details</Th>
              </tr>
            </thead>
            <tbody>
              {audit.data.map((row) => (
                <tr key={row.id}>
                  <Td className="text-xs whitespace-nowrap">{when(row.created_at)}</Td>
                  <Td className="text-xs">{row.operator}</Td>
                  <Td className="text-xs">{row.action.replaceAll("_", " ").toLowerCase()}</Td>
                  <Td className="text-xs">
                    {row.target_type} <span className="font-mono">{row.target_id}</span>
                  </Td>
                  <Td className="font-mono text-xs break-all text-neutral-600">
                    {Object.keys(row.data).length ? JSON.stringify(row.data) : ""}
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
