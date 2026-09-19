import {
  Button,
  Card,
  CriticalityBadge,
  Dialog,
  ErrorMessage,
  Input,
  Notice,
  PageHeader,
  Select,
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
import {
  CRITICALITIES,
  RULES,
  when,
  type Criticality,
  type Rule,
  type RuleSettings,
} from "./shared";

/** A served definition's attributes, as far as the console shows them (D52). */
interface Entry extends RuleSettings {
  key: string;
  type: string;
  unit?: string | null;
  labels: { en: string };
}

function entriesOf(definition: Record<string, unknown>): Entry[] {
  return definition.attributes as Entry[];
}

function settingsOf(entry: RuleSettings): RuleSettings {
  return {
    criticality: entry.criticality,
    rule: entry.rule,
    tolerance: entry.tolerance ?? null,
    shareable: entry.shareable,
  };
}

function same(a: RuleSettings, b: RuleSettings): boolean {
  return JSON.stringify(settingsOf(a)) === JSON.stringify(settingsOf(b));
}

export function TemplatesPage() {
  const { session } = useSession();
  const templates = useQuery({
    queryKey: ["admin", "templates"],
    queryFn: () => session.call((hub) => hub.GET("/api/v1/templates")),
  });
  if (templates.isPending) return <Spinner />;
  return (
    <>
      <PageHeader title="Category templates" />
      <Card>
        <Table>
          <thead>
            <tr>
              <Th>Category</Th>
              <Th>Attributes</Th>
              <Th>Last change</Th>
              <Th>Hash</Th>
            </tr>
          </thead>
          <tbody>
            {(templates.data ?? []).map((template) => (
              <tr key={template.code}>
                <Td>
                  <Link to={`/templates/${template.code}`} className="text-accent hover:underline">
                    {template.code}
                  </Link>
                </Td>
                <Td>{entriesOf(template.definition).length}</Td>
                <Td className="text-xs">
                  {template.change_note ?? "–"}
                  <p className="text-neutral-500">{when(template.updated_at)}</p>
                </Td>
                <Td className="font-mono text-xs">{template.definition_hash.slice(0, 12)}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      </Card>
    </>
  );
}

/** How one category compares: only an operator changes it (§7.2). */
export function TemplatePage() {
  const { code = "" } = useParams();
  const { session } = useSession();
  const template = useQuery({
    queryKey: ["admin", "template", code],
    queryFn: () =>
      session.call((hub) => hub.GET("/api/v1/templates/{code}", { params: { path: { code } } })),
  });
  if (template.isPending) return <Spinner />;
  if (!template.data) return <ErrorMessage error={template.error} />;
  return (
    <TemplateEditor
      key={template.data.definition_hash}
      code={code}
      hash={template.data.definition_hash}
      entries={entriesOf(template.data.definition)}
    />
  );
}

/** One row of the editor: an attribute of the category, one being added, or one removed. */
interface Row {
  key: string;
  label: string;
  type: string;
  settings: RuleSettings;
  added: boolean;
  removed: boolean;
}

const NEW_SETTINGS: RuleSettings = {
  criticality: "minor",
  rule: "exact",
  tolerance: null,
  shareable: true,
};

function TemplateEditor({ code, hash, entries }: { code: string; hash: string; entries: Entry[] }) {
  const [rows, setRows] = useState<Row[]>(() =>
    entries.map((entry) => ({
      key: entry.key,
      label: entry.labels.en,
      type: entry.type,
      settings: settingsOf(entry),
      added: false,
      removed: false,
    })),
  );
  const [saving, setSaving] = useState(false);

  const original = new Map(entries.map((entry) => [entry.key, settingsOf(entry)]));
  const kept = rows.filter((row) => !row.added && !row.removed);
  const body = {
    set: Object.fromEntries(
      kept
        .filter((row) => {
          const before = original.get(row.key);
          return before !== undefined && !same(before, row.settings);
        })
        .map((row) => [row.key, row.settings]),
    ),
    add: Object.fromEntries(rows.filter((row) => row.added).map((row) => [row.key, row.settings])),
    remove: rows.filter((row) => row.removed).map((row) => row.key),
  };
  const dirty =
    Object.keys(body.set).length + Object.keys(body.add).length + body.remove.length > 0;

  function update(key: string, patch: Partial<RuleSettings>) {
    setRows(
      rows.map((row) =>
        row.key === key ? { ...row, settings: { ...row.settings, ...patch } } : row,
      ),
    );
  }

  function toggle(key: string) {
    // An attribute being added simply goes away again; an existing one is marked for removal.
    setRows(
      rows.flatMap((row) =>
        row.key !== key ? [row] : row.added ? [] : [{ ...row, removed: !row.removed }],
      ),
    );
  }

  return (
    <>
      <PageHeader title={code}>
        <span title="Definition hash" className="font-mono text-xs text-neutral-500">
          {hash.slice(0, 12)}
        </span>
        <Button
          disabled={!dirty}
          onClick={() => {
            setSaving(true);
          }}
        >
          Save changes
        </Button>
      </PageHeader>
      <Card>
        <Table>
          <thead>
            <tr>
              <Th>Attribute</Th>
              <Th>Criticality</Th>
              <Th>Rule</Th>
              <Th>Tolerance</Th>
              <Th>Shareable</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {rows.map(({ key, label, type, settings, removed: gone }) => {
              return (
                <tr key={key} className={gone ? "opacity-40" : undefined}>
                  <Td>
                    {label} <span className="font-mono text-xs text-neutral-500">{key}</span>
                    <p className="text-xs text-neutral-500">{type}</p>
                  </Td>
                  <Td>
                    <Select
                      aria-label={`${key} criticality`}
                      value={settings.criticality}
                      disabled={gone}
                      onChange={(event) => {
                        update(key, { criticality: event.target.value as Criticality });
                      }}
                    >
                      {CRITICALITIES.map((value) => (
                        <option key={value}>{value}</option>
                      ))}
                    </Select>
                  </Td>
                  <Td>
                    <Select
                      aria-label={`${key} rule`}
                      value={settings.rule}
                      disabled={gone}
                      onChange={(event) => {
                        const rule = event.target.value as Rule;
                        update(key, { rule, tolerance: rule === "tolerance" ? 0 : null });
                      }}
                    >
                      {RULES.map((value) => (
                        <option key={value}>{value}</option>
                      ))}
                    </Select>
                  </Td>
                  <Td>
                    {settings.rule === "tolerance" && (
                      <Input
                        aria-label={`${key} tolerance`}
                        inputMode="decimal"
                        className="w-24"
                        value={String(settings.tolerance ?? "")}
                        onChange={(event) => {
                          update(key, { tolerance: Number(event.target.value) });
                        }}
                      />
                    )}
                  </Td>
                  <Td>
                    <input
                      type="checkbox"
                      aria-label={`${key} shareable`}
                      checked={settings.shareable}
                      disabled={gone}
                      onChange={(event) => {
                        update(key, { shareable: event.target.checked });
                      }}
                    />
                  </Td>
                  <Td className="text-right">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        toggle(key);
                      }}
                    >
                      {gone ? "Keep" : "Remove"}
                    </Button>
                  </Td>
                </tr>
              );
            })}
          </tbody>
        </Table>
        <AddAttribute
          taken={rows.map((row) => row.key)}
          onAdd={(key) => {
            setRows([
              ...rows,
              { key, label: "new", type: "", settings: NEW_SETTINGS, added: true, removed: false },
            ]);
          }}
        />
      </Card>
      {saving && (
        <SaveDialog
          code={code}
          body={body}
          onClose={() => {
            setSaving(false);
          }}
        />
      )}
    </>
  );
}

function AddAttribute({ taken, onAdd }: { taken: string[]; onAdd: (key: string) => void }) {
  const { session } = useSession();
  const [key, setKey] = useState("");
  const attributes = useQuery({
    queryKey: ["admin", "attributes", "APPROVED"],
    queryFn: () =>
      session.call((hub) =>
        hub.GET("/api/v1/attributes", { params: { query: { status: "APPROVED" } } }),
      ),
  });
  const addable = (attributes.data ?? []).filter(
    (attribute) => attribute.kind === "ATTRIBUTE" && !taken.includes(attribute.key),
  );
  return (
    <div className="mt-4 flex items-end gap-2">
      <div className="w-80">
        <Field label="Add an approved attribute" id="add-attribute">
          <Select
            id="add-attribute"
            value={key}
            onChange={(event) => {
              setKey(event.target.value);
            }}
          >
            <option value="">Choose…</option>
            {addable.map((attribute) => (
              <option key={attribute.key} value={attribute.key}>
                {attribute.key}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Button
        variant="secondary"
        disabled={!key}
        onClick={() => {
          onAdd(key);
          setKey("");
        }}
      >
        Add
      </Button>
    </div>
  );
}

function SaveDialog({
  code,
  body,
  onClose,
}: {
  code: string;
  body: { set: Record<string, RuleSettings>; add: Record<string, RuleSettings>; remove: string[] };
  onClose: () => void;
}) {
  const { session } = useSession();
  const queries = useQueryClient();
  const [note, setNote] = useState("");
  const save = useMutation({
    mutationFn: () =>
      session.call((hub) =>
        hub.PATCH("/api/v1/admin/templates/{code}", {
          params: { path: { code } },
          body: { ...body, change_note: note },
        }),
      ),
    onSuccess: async () => {
      await queries.invalidateQueries({ queryKey: ["admin"] });
      onClose();
    },
  });
  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
      title={`Change ${code}`}
      footer={
        <Button
          disabled={!note.trim() || save.isPending}
          onClick={() => {
            save.mutate();
          }}
        >
          Save
        </Button>
      }
    >
      <div className="space-y-3">
        <Notice>
          Every family of the category is re-projected now; nodes pick the definition up at their
          next sync, and open assessments use it in their next round.
        </Notice>
        <ul className="text-sm">
          {Object.entries(body.set).map(([key, settings]) => (
            <li key={key}>
              {key}: <CriticalityBadge criticality={settings.criticality} /> {settings.rule}
            </li>
          ))}
          {Object.keys(body.add).map((key) => (
            <li key={key}>+ {key}</li>
          ))}
          {body.remove.map((key) => (
            <li key={key}>− {key}</li>
          ))}
        </ul>
        <Field label="Change note" id="change-note">
          <Textarea
            id="change-note"
            value={note}
            onChange={(event) => {
              setNote(event.target.value);
            }}
          />
        </Field>
        <ErrorMessage error={save.error} />
      </div>
    </Dialog>
  );
}
