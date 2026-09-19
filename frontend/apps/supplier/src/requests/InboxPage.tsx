import { Card, Empty, PageHeader, Spinner, StatusBadge, Table, Td, Th } from "@sanovio/ui";
import { Link } from "react-router";

import { useRequests } from "./queries";

/** Requests about our products; a hospital appears only under its alias (§8.6). */
export function InboxPage() {
  const requests = useRequests();
  return (
    <>
      <PageHeader title="Requests" />
      <Card>
        {requests.isPending ? (
          <Spinner />
        ) : !requests.data?.length ? (
          <Empty>No requests yet.</Empty>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Product</Th>
                <Th>Hospital</Th>
                <Th>Questions</Th>
                <Th>Status</Th>
              </tr>
            </thead>
            <tbody>
              {requests.data.map((request) => {
                const open = request.questions.filter((q) => q.status === "SENT").length;
                return (
                  <tr key={request.assessment_id}>
                    <Td>
                      <Link
                        to={`/requests/${request.assessment_id}`}
                        className="text-accent hover:underline"
                      >
                        {request.variant_label}
                      </Link>
                      <div className="text-xs text-neutral-500">
                        {request.family} · {request.article_no}
                      </div>
                    </Td>
                    <Td>{request.hospital}</Td>
                    <Td>{open ? `${open} open` : `${request.questions.length} answered`}</Td>
                    <Td>
                      <StatusBadge status={request.status} />
                    </Td>
                  </tr>
                );
              })}
            </tbody>
          </Table>
        )}
      </Card>
    </>
  );
}
