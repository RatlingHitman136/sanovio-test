import { ApiError } from "@sanovio/api";
import { render, screen } from "@testing-library/react";

import { ErrorMessage, describeError } from "./feedback";

test("a conflict shows its message and code", () => {
  const error = new ApiError(409, {
    detail: "attribute proposals are still running",
    code: "ATTRIBUTE_PROPOSAL_PENDING",
  });
  expect(describeError(error)).toBe(
    "attribute proposals are still running (ATTRIBUTE_PROPOSAL_PENDING)",
  );
});

test("a version conflict is explained in plain words", () => {
  const error = new ApiError(409, { detail: "stale", code: "VERSION_CONFLICT" });
  expect(describeError(error)).toMatch(/changed this in the meantime/);
});

test("validation errors name the field", () => {
  const error = new ApiError(422, {
    detail: [{ loc: ["body", "note"], msg: "Field required" }],
  });
  render(<ErrorMessage error={error} />);
  expect(screen.getByRole("alert")).toHaveTextContent("note: Field required");
});
