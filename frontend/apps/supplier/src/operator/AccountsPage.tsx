import type { HubSchemas } from "@sanovio/api";
import {
  Badge,
  Button,
  Card,
  CardTitle,
  Dialog,
  ErrorMessage,
  Input,
  PageHeader,
  Select,
  Spinner,
  Table,
  Td,
  Th,
} from "@sanovio/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { useSession } from "../sessionContext";
import { Field } from "./Field";

type User = HubSchemas["schemas"]["UserView"];

const MIN_PASSWORD = 6;

type Open = { kind: "supplier" } | { kind: "user" } | { kind: "password"; user: User } | null;

/** Hub logins: suppliers' catalog teams and the operators. Hospital staff sign in at their node. */
export function AccountsPage() {
  const { session } = useSession();
  const queries = useQueryClient();
  const [open, setOpen] = useState<Open>(null);
  const organizations = useQuery({
    queryKey: ["admin", "organizations"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/admin/organizations")),
  });
  const users = useQuery({
    queryKey: ["admin", "users"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/admin/users")),
  });
  const active = useMutation({
    mutationFn: (user: User) =>
      session.call((hub) => {
        const params = { params: { path: { user_id: user.id } } };
        return user.is_active
          ? hub.POST("/api/v1/admin/users/{user_id}/deactivate", params)
          : hub.POST("/api/v1/admin/users/{user_id}/reactivate", params);
      }),
    onSuccess: () => queries.invalidateQueries({ queryKey: ["admin", "users"] }),
  });
  const close = () => {
    setOpen(null);
  };

  if (organizations.isPending || users.isPending) return <Spinner />;
  return (
    <>
      <PageHeader title="Accounts">
        <Button
          variant="secondary"
          onClick={() => {
            setOpen({ kind: "supplier" });
          }}
        >
          New supplier
        </Button>
        <Button
          onClick={() => {
            setOpen({ kind: "user" });
          }}
        >
          New user
        </Button>
      </PageHeader>
      <div className="space-y-4">
        {(organizations.data ?? []).map((org) => (
          <Card key={org.id}>
            <CardTitle>
              {org.name} <Badge>{org.type.toLowerCase()}</Badge>
            </CardTitle>
            <Table>
              <thead>
                <tr>
                  <Th>User</Th>
                  <Th>Email</Th>
                  <Th>State</Th>
                  <Th />
                </tr>
              </thead>
              <tbody>
                {(users.data ?? [])
                  .filter((user) => user.org_id === org.id)
                  .map((user) => (
                    <tr key={user.id}>
                      <Td>{user.display_name}</Td>
                      <Td>{user.email}</Td>
                      <Td>
                        <Badge tone={user.is_active ? "good" : "neutral"}>
                          {user.is_active ? "active" : "deactivated"}
                        </Badge>
                      </Td>
                      <Td className="space-x-1 text-right whitespace-nowrap">
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => {
                            setOpen({ kind: "password", user });
                          }}
                        >
                          Reset password
                        </Button>
                        <Button
                          size="sm"
                          variant={user.is_active ? "danger" : "secondary"}
                          disabled={active.isPending}
                          onClick={() => {
                            active.mutate(user);
                          }}
                        >
                          {user.is_active ? "Deactivate" : "Reactivate"}
                        </Button>
                      </Td>
                    </tr>
                  ))}
              </tbody>
            </Table>
          </Card>
        ))}
      </div>
      <ErrorMessage error={active.error} />
      {open?.kind === "supplier" && <NewSupplier onClose={close} />}
      {open?.kind === "user" && (
        <NewUser organizations={organizations.data ?? []} onClose={close} />
      )}
      {open?.kind === "password" && <ResetPassword user={open.user} onClose={close} />}
    </>
  );
}

function FormDialog({
  title,
  ready,
  pending,
  error,
  onSubmit,
  onClose,
  children,
}: {
  title: string;
  ready: boolean;
  pending: boolean;
  error: unknown;
  onSubmit: () => void;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <Dialog
      open
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
      title={title}
      footer={
        <Button disabled={!ready || pending} onClick={onSubmit}>
          Save
        </Button>
      }
    >
      <div className="space-y-3">
        {children}
        <ErrorMessage error={error} />
      </div>
    </Dialog>
  );
}

function useAccountsMutation<T>(call: () => Promise<T>, onClose: () => void) {
  const queries = useQueryClient();
  return useMutation({
    mutationFn: call,
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
  });
}

function NewSupplier({ onClose }: { onClose: () => void }) {
  const { session } = useSession();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const create = useAccountsMutation(
    () => session.call((hub) => hub.POST("/api/v1/admin/suppliers", { body: { code, name } })),
    onClose,
  );
  return (
    <FormDialog
      title="New supplier"
      ready={code !== "" && name !== ""}
      pending={create.isPending}
      error={create.error}
      onSubmit={() => {
        create.mutate();
      }}
      onClose={onClose}
    >
      <Field label="Code, e.g. org_terumo" id="code">
        <Input
          id="code"
          value={code}
          onChange={(event) => {
            setCode(event.target.value);
          }}
        />
      </Field>
      <Field label="Name" id="name">
        <Input
          id="name"
          value={name}
          onChange={(event) => {
            setName(event.target.value);
          }}
        />
      </Field>
    </FormDialog>
  );
}

function NewUser({
  organizations,
  onClose,
}: {
  organizations: HubSchemas["schemas"]["OrganizationView"][];
  onClose: () => void;
}) {
  const { session } = useSession();
  const [form, setForm] = useState({
    org_id: organizations[0]?.id ?? "",
    email: "",
    display_name: "",
    password: "",
  });
  const create = useAccountsMutation(
    () => session.call((hub) => hub.POST("/api/v1/admin/users", { body: form })),
    onClose,
  );
  const text = (name: "email" | "display_name" | "password", label: string) => (
    <Field label={label} id={name}>
      <Input
        id={name}
        type={name === "password" ? "password" : "text"}
        value={form[name]}
        onChange={(event) => {
          setForm({ ...form, [name]: event.target.value });
        }}
      />
    </Field>
  );
  return (
    <FormDialog
      title="New user"
      ready={
        form.org_id !== "" &&
        form.email.includes("@") &&
        form.display_name !== "" &&
        form.password.length >= MIN_PASSWORD
      }
      pending={create.isPending}
      error={create.error}
      onSubmit={() => {
        create.mutate();
      }}
      onClose={onClose}
    >
      <Field label="Organization (the role follows it)" id="org">
        <Select
          id="org"
          value={form.org_id}
          onChange={(event) => {
            setForm({ ...form, org_id: event.target.value });
          }}
        >
          {organizations.map((org) => (
            <option key={org.id} value={org.id}>
              {org.name} ({org.type.toLowerCase()})
            </option>
          ))}
        </Select>
      </Field>
      {text("email", "Email")}
      {text("display_name", "Name")}
      {text("password", `Password (at least ${MIN_PASSWORD} characters, pass it on yourself)`)}
    </FormDialog>
  );
}

function ResetPassword({ user, onClose }: { user: User; onClose: () => void }) {
  const { session } = useSession();
  const [password, setPassword] = useState("");
  const reset = useAccountsMutation(
    () =>
      session.call((hub) =>
        hub.POST("/api/v1/admin/users/{user_id}/password", {
          params: { path: { user_id: user.id } },
          body: { password },
        }),
      ),
    onClose,
  );
  return (
    <FormDialog
      title={`New password for ${user.email}`}
      ready={password.length >= MIN_PASSWORD}
      pending={reset.isPending}
      error={reset.error}
      onSubmit={() => {
        reset.mutate();
      }}
      onClose={onClose}
    >
      <p className="text-sm text-neutral-600">Their open sessions end at once.</p>
      <Field label="New password" id="new-password">
        <Input
          id="new-password"
          type="password"
          value={password}
          onChange={(event) => {
            setPassword(event.target.value);
          }}
        />
      </Field>
    </FormDialog>
  );
}
