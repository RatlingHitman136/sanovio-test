import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { ValueInput, formatValue, type ExpectedAnswer, type TypedValue } from "./values";

function Harness({ expected, seen }: { expected: ExpectedAnswer; seen: (TypedValue | null)[] }) {
  const [value, setValue] = useState<TypedValue | null>(null);
  return (
    <ValueInput
      label="answer"
      expected={expected}
      value={value}
      onChange={(next) => {
        seen.push(next);
        setValue(next);
      }}
    />
  );
}

async function enter(expected: ExpectedAnswer, act: (field: HTMLElement) => Promise<void>) {
  const seen: (TypedValue | null)[] = [];
  render(<Harness expected={expected} seen={seen} />);
  await act(screen.getByLabelText("answer"));
  return seen.at(-1);
}

test("a yes/no answer becomes a bool", async () => {
  const value = await enter({ type: "bool" }, (field) => userEvent.selectOptions(field, "yes"));
  expect(value).toEqual({ type: "bool", value: true });
});

test("an option is chosen by its code", async () => {
  const value = await enter({ type: "enum", options: ["REGULAR", "THIN"] }, (field) =>
    userEvent.selectOptions(field, "THIN"),
  );
  expect(value).toEqual({ type: "enum", value: "THIN" });
});

test("a number carries the unit the question asks for", async () => {
  const value = await enter({ type: "number", unit: "mm" }, (field) =>
    userEvent.type(field, "0.58"),
  );
  expect(value).toEqual({ type: "number", value: 0.58, unit: "mm" });
  expect(screen.getByText("mm")).toBeInTheDocument();
});

test("a list is typed comma-separated", async () => {
  const value = await enter({ type: "list" }, (field) =>
    userEvent.type(field, "ISO 7886-1, ISO 80369-7"),
  );
  expect(value).toEqual({ type: "list", value: ["ISO 7886-1", "ISO 80369-7"] });
});

test("an identifier keeps its scheme; the hub computes the check digit", async () => {
  const value = await enter({ type: "identifier", scheme: "GTIN" }, (field) =>
    userEvent.type(field, "04040456789018"),
  );
  expect(value).toEqual({
    type: "identifier",
    scheme: "GTIN",
    value: "04040456789018",
    checksum_valid: null,
  });
});

test("free text is text, and clearing it gives no value", async () => {
  const seen: (TypedValue | null)[] = [];
  render(<Harness expected={{ type: "text" }} seen={seen} />);
  const field = screen.getByLabelText("answer");
  await userEvent.type(field, "keine");
  expect(seen.at(-1)).toEqual({ type: "text", value: "keine" });
  await userEvent.clear(field);
  expect(seen.at(-1)).toBeNull();
});

test.each([
  [{ type: "bool", value: false }, "no"],
  [{ type: "number", value: 10, unit: "ml" }, "10 ml"],
  [{ type: "list", value: ["ISO 7864"] }, "ISO 7864"],
  [{ type: "identifier", scheme: "GTIN", value: "0404" }, "GTIN 0404"],
  [{ type: "enum", value: "LUER_LOCK" }, "LUER_LOCK"],
  [null, "–"],
])("formatValue(%j) is %s", (value, shown) => {
  expect(formatValue(value)).toBe(shown);
});
