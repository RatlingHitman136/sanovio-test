import { ApiError } from "@sanovio/api";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { SignIn } from "./shell";

test("a refused sign-in shows why and lets the user try again", async () => {
  const attempts: string[] = [];
  render(
    <SignIn
      title="Purchaser"
      onSignIn={(email) => {
        attempts.push(email);
        return Promise.reject(new ApiError(401, { detail: "invalid email or password" }));
      }}
    />,
  );

  await userEvent.type(screen.getByLabelText("Email"), "anna.meier@demo-ksp.example");
  await userEvent.type(screen.getByLabelText("Password"), "wrong");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("invalid email or password");
  expect(attempts).toEqual(["anna.meier@demo-ksp.example"]);
  expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled();
});
