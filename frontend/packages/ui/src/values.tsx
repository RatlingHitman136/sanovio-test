/**
 * Typed values as both services exchange them (core `values.py`), shown and entered.
 * The input's shape comes from a question's `expected_answer`, so a supplier or purchaser
 * can only give a value the hub will accept.
 */
import { useId, useState } from "react";

import { Input, Select } from "./primitives";

export type TypedValue =
  | { type: "bool"; value: boolean }
  | { type: "number"; value: number; unit: string }
  | { type: "enum"; value: string }
  | { type: "text"; value: string }
  | { type: "list"; value: string[] }
  | { type: "identifier"; scheme: string; value: string; checksum_valid?: boolean | null };

export interface ExpectedAnswer {
  type: string;
  unit?: string;
  options?: string[];
  scheme?: string;
}

function isTyped(value: unknown): value is TypedValue {
  return typeof value === "object" && value !== null && "type" in value && "value" in value;
}

/** A readable form of a typed value; anything unexpected is shown as JSON, never dropped. */
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return "–";
  if (!isTyped(value)) return JSON.stringify(value);
  switch (value.type) {
    case "bool":
      return value.value ? "yes" : "no";
    case "number":
      return `${value.value} ${value.unit}`.trim();
    case "list":
      return value.value.join(", ");
    case "identifier":
      return `${value.scheme} ${value.value}`;
    default:
      return value.value;
  }
}

export function ValueView({ value }: { value: unknown }) {
  return <span className="font-mono text-[13px]">{formatValue(value)}</span>;
}

interface ValueInputProps {
  expected: ExpectedAnswer;
  value: TypedValue | null;
  onChange: (value: TypedValue | null) => void;
  disabled?: boolean;
  label: string;
}

/** Emits a typed value, or null while nothing valid is entered. */
export function ValueInput({ expected, value, onChange, disabled, label }: ValueInputProps) {
  const id = useId();
  const current = value?.value;
  switch (expected.type) {
    case "bool":
      return (
        <Select
          aria-label={label}
          id={id}
          disabled={disabled}
          value={typeof current === "boolean" ? String(current) : ""}
          onChange={(event) => {
            const choice = event.target.value;
            onChange(choice === "" ? null : { type: "bool", value: choice === "true" });
          }}
        >
          <option value="">–</option>
          <option value="true">yes</option>
          <option value="false">no</option>
        </Select>
      );
    case "enum":
      return (
        <Select
          aria-label={label}
          id={id}
          disabled={disabled}
          value={typeof current === "string" ? current : ""}
          onChange={(event) => {
            const choice = event.target.value;
            onChange(choice === "" ? null : { type: "enum", value: choice });
          }}
        >
          <option value="">–</option>
          {(expected.options ?? []).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </Select>
      );
    case "number":
      return (
        <div className="flex items-center gap-2">
          <Input
            aria-label={label}
            id={id}
            type="number"
            step="any"
            disabled={disabled}
            value={typeof current === "number" ? current : ""}
            onChange={(event) => {
              const number = event.target.valueAsNumber;
              onChange(
                Number.isNaN(number)
                  ? null
                  : { type: "number", value: number, unit: expected.unit ?? "" },
              );
            }}
          />
          {expected.unit && <span className="text-sm text-neutral-500">{expected.unit}</span>}
        </div>
      );
    case "list":
      return (
        <ListInput
          label={label}
          id={id}
          disabled={disabled}
          initial={Array.isArray(current) ? current : []}
          onChange={onChange}
        />
      );
    case "identifier":
      return (
        <Input
          aria-label={label}
          id={id}
          placeholder={expected.scheme}
          disabled={disabled}
          value={typeof current === "string" ? current : ""}
          onChange={(event) => {
            const text = event.target.value.trim();
            onChange(
              text
                ? {
                    type: "identifier",
                    scheme: expected.scheme ?? "",
                    value: text,
                    checksum_valid: null,
                  }
                : null,
            );
          }}
        />
      );
    default:
      return (
        <Input
          aria-label={label}
          id={id}
          disabled={disabled}
          value={typeof current === "string" ? current : ""}
          onChange={(event) => {
            const text = event.target.value;
            onChange(text.trim() ? { type: "text", value: text } : null);
          }}
        />
      );
  }
}

interface ListInputProps {
  label: string;
  id: string;
  disabled: boolean | undefined;
  initial: string[];
  onChange: (value: TypedValue | null) => void;
}

/** Keeps what is typed, commas and spaces included; only the emitted value is parsed. */
function ListInput({ label, id, disabled, initial, onChange }: ListInputProps) {
  const [text, setText] = useState(initial.join(", "));
  return (
    <Input
      aria-label={label}
      id={id}
      placeholder="comma-separated"
      disabled={disabled}
      value={text}
      onChange={(event) => {
        setText(event.target.value);
        const items = event.target.value
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean);
        onChange(items.length ? { type: "list", value: items } : null);
      }}
    />
  );
}
