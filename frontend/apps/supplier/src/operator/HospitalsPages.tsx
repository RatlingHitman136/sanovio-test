import {
  Badge,
  Button,
  Card,
  CardTitle,
  Dialog,
  Empty,
  ErrorMessage,
  Input,
  Notice,
  PageHeader,
  Spinner,
  Table,
  Td,
  Textarea,
  Th,
} from "@sanovio/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router";

import { useSession } from "../sessionContext";
import { Field } from "./Field";
import { when } from "./shared";

export function HospitalsPage() {
  const { session } = useSession();
  const [creating, setCreating] = useState(false);
  const tenants = useQuery({
    queryKey: ["admin", "tenants"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/admin/tenants")),
  });
  return (
    <>
      <PageHeader title="Hospitals">
        <Button
          onClick={() => {
            setCreating(true);
          }}
        >
          New hospital
        </Button>
      </PageHeader>
      <Card>
        {tenants.isPending ? (
          <Spinner />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>Hospital</Th>
                <Th>Code (node signs as)</Th>
                <Th>Suppliers see</Th>
              </tr>
            </thead>
            <tbody>
              {(tenants.data ?? []).map((tenant) => (
                <tr key={tenant.id}>
                  <Td>
                    <Link to={`/hospitals/${tenant.id}`} className="text-accent hover:underline">
                      {tenant.name}
                    </Link>
                  </Td>
                  <Td className="font-mono text-xs">{tenant.code}</Td>
                  <Td>
                    {tenant.disclose_name_to_suppliers ? tenant.name : tenant.supplier_facing_alias}
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      {creating && (
        <NewHospital
          onClose={() => {
            setCreating(false);
          }}
        />
      )}
    </>
  );
}

function NewHospital({ onClose }: { onClose: () => void }) {
  const { session } = useSession();
  const queries = useQueryClient();
  const [form, setForm] = useState({ code: "", name: "", alias: "" });
  const create = useMutation({
    mutationFn: () =>
      session.call((hub) =>
        hub.POST("/api/v1/admin/tenants", {
          body: {
            code: form.code,
            name: form.name,
            supplier_facing_alias: form.alias,
            disclose_name_to_suppliers: false,
            language: "de",
          },
        }),
      ),
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: ["admin", "tenants"] });
      onClose();
    },
  });
  const input = (name: keyof typeof form, label: string) => (
    <Field label={label} id={name}>
      <Input
        id={name}
        value={form[name]}
        onChange={(event) => {
          setForm({ ...form, [name]: event.target.value });
        }}
      />
    </Field>
  );
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="New hospital"
      footer={
        <Button
          disabled={!form.code || !form.name || !form.alias || create.isPending}
          onClick={() => {
            create.mutate();
          }}
        >
          Create
        </Button>
      }
    >
      <div className="space-y-3">
        {input("code", "Code, e.g. ten_ksp")}
        {input("name", "Name")}
        {input("alias", "Alias suppliers see, e.g. Hospital H-7F3A")}
        <ErrorMessage error={create.error} />
      </div>
    </Dialog>
  );
}

/** The keys the hub trusts for this hospital, and its purchasers as the hub knows them. */
export function HospitalPage() {
  const { tenantId = "" } = useParams();
  const { session } = useSession();
  const queries = useQueryClient();
  const [registering, setRegistering] = useState(false);
  const tenant = { params: { path: { tenant_id: tenantId } } };
  const tenants = useQuery({
    queryKey: ["admin", "tenants"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/admin/tenants")),
  });
  const keys = useQuery({
    queryKey: ["admin", "keys", tenantId],
    queryFn: () =>
      session.call((hub) => hub.GET("/api/v1/admin/tenants/{tenant_id}/signing-keys", tenant)),
  });
  const principals = useQuery({
    queryKey: ["admin", "principals", tenantId],
    queryFn: () =>
      session.call((hub) => hub.GET("/api/v1/admin/tenants/{tenant_id}/principals", tenant)),
  });
  const refresh = () => queries.invalidateQueries({ queryKey: ["admin"] });
  const revoke = useMutation({
    mutationFn: (kid: string) =>
      session.call((hub) =>
        hub.POST("/api/v1/admin/tenants/{tenant_id}/signing-keys/{kid}/revoke", {
          params: { path: { tenant_id: tenantId, kid } },
        }),
      ),
    onSuccess: refresh,
  });
  const block = useMutation({
    mutationFn: ({ subject, blocked }: { subject: string; blocked: boolean }) =>
      session.call((hub) => {
        const params = { params: { path: { tenant_id: tenantId, subject_id: subject } } };
        return blocked
          ? hub.POST("/api/v1/admin/tenants/{tenant_id}/principals/{subject_id}/unblock", params)
          : hub.POST("/api/v1/admin/tenants/{tenant_id}/principals/{subject_id}/block", params);
      }),
    onSuccess: refresh,
  });
  const hospital = tenants.data?.find((row) => row.id === tenantId);

  return (
    <>
      <PageHeader title={hospital?.name ?? "Hospital"} />
      <div className="space-y-4">
        <Card>
          <div className="mb-3 flex items-center justify-between">
            <CardTitle className="mb-0">Node signing keys</CardTitle>
            <Button
              variant="secondary"
              onClick={() => {
                setRegistering(true);
              }}
            >
              Register key
            </Button>
          </div>
          {!keys.data?.length ? (
            <Empty>No key: this hospital's purchasers cannot reach the hub yet.</Empty>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Key id</Th>
                  <Th>Fingerprint</Th>
                  <Th>Valid from</Th>
                  <Th>State</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {keys.data.map((key) => (
                  <tr key={key.kid}>
                    <Td className="font-mono text-xs">{key.kid}</Td>
                    <Td className="font-mono text-xs break-all">{key.fingerprint}</Td>
                    <Td className="text-xs">{when(key.not_before)}</Td>
                    <Td>
                      {key.revoked_at ? (
                        <Badge tone="bad">revoked</Badge>
                      ) : (
                        <Badge tone="good">trusted</Badge>
                      )}
                    </Td>
                    <Td className="text-right">
                      {!key.revoked_at && (
                        <Button
                          size="sm"
                          variant="danger"
                          disabled={revoke.isPending}
                          onClick={() => {
                            if (
                              window.confirm(`Revoke ${key.kid}? Its purchasers are signed out.`)
                            ) {
                              revoke.mutate(key.kid);
                            }
                          }}
                        >
                          Revoke
                        </Button>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          <ErrorMessage error={revoke.error} />
        </Card>
        <Card>
          <CardTitle>Purchasers</CardTitle>
          <p className="mb-3 text-xs text-neutral-500">
            Pseudonymous: the hub never learns a purchaser's name.
          </p>
          {!principals.data?.length ? (
            <Empty>No purchaser has signed in yet.</Empty>
          ) : (
            <Table>
              <thead>
                <tr>
                  <Th>Subject</Th>
                  <Th>First seen</Th>
                  <Th>Last seen</Th>
                  <Th>Assessments</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {principals.data.map((principal) => (
                  <tr key={principal.subject_id}>
                    <Td className="font-mono text-xs">{principal.subject_id}</Td>
                    <Td className="text-xs">{when(principal.first_seen_at)}</Td>
                    <Td className="text-xs">{when(principal.last_seen_at)}</Td>
                    <Td>{principal.assessments}</Td>
                    <Td className="text-right">
                      <Button
                        size="sm"
                        variant={principal.is_blocked ? "secondary" : "danger"}
                        disabled={block.isPending}
                        onClick={() => {
                          block.mutate({
                            subject: principal.subject_id,
                            blocked: principal.is_blocked,
                          });
                        }}
                      >
                        {principal.is_blocked ? "Unblock" : "Block"}
                      </Button>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
          <ErrorMessage error={block.error} />
        </Card>
      </div>
      {registering && (
        <RegisterKey
          tenantId={tenantId}
          onClose={() => {
            setRegistering(false);
          }}
        />
      )}
    </>
  );
}

function RegisterKey({ tenantId, onClose }: { tenantId: string; onClose: () => void }) {
  const { session } = useSession();
  const queries = useQueryClient();
  const [jwk, setJwk] = useState("");
  const parsed = parseJwk(jwk);
  const register = useMutation({
    mutationFn: () =>
      session.call((hub) =>
        hub.POST("/api/v1/admin/tenants/{tenant_id}/signing-keys", {
          params: { path: { tenant_id: tenantId } },
          body: { public_jwk: parsed ?? {} },
        }),
      ),
    onSuccess: () => queries.invalidateQueries({ queryKey: ["admin", "keys", tenantId] }),
  });
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title="Register a node key"
      footer={
        !register.data && (
          <Button
            disabled={!parsed || register.isPending}
            onClick={() => {
              register.mutate();
            }}
          >
            Register
          </Button>
        )
      }
    >
      <div className="space-y-3">
        {register.data ? (
          <>
            <Notice>
              Registered. Read this fingerprint to the hospital by phone; it must match the one
              their node shows.
            </Notice>
            <p className="font-mono text-sm break-all">{register.data.fingerprint}</p>
          </>
        ) : (
          <Field label="Public JWK, as the node's admin page shows it" id="jwk">
            <Textarea
              id="jwk"
              className="font-mono text-xs"
              value={jwk}
              onChange={(event) => {
                setJwk(event.target.value);
              }}
            />
          </Field>
        )}
        <ErrorMessage error={register.error} />
      </div>
    </Dialog>
  );
}

function parseJwk(text: string): Record<string, string> | null {
  try {
    const value: unknown = JSON.parse(text);
    return value && typeof value === "object" ? (value as Record<string, string>) : null;
  } catch {
    return null;
  }
}
