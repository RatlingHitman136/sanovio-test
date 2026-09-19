import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "e2e-demo-password";
const HUB_APP = "http://127.0.0.1:15174";

async function signIn(page: Page, email: string, password = PASSWORD) {
  await page.goto(HUB_APP);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

// The needle template, so scenario 1 (syringes) runs on the seeded settings whatever the order.
test("the operator changes a criticality and the template gets a new hash", async ({ page }) => {
  await signIn(page, "ops@sanovio-demo.example");
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();

  await page.getByRole("link", { name: "Templates" }).click();
  await page.getByRole("link", { name: "hypodermic_needle" }).click();
  const header = page.getByTitle("Definition hash");
  const before = await header.textContent();
  await page.getByLabel("wall_type criticality").selectOption("minor");
  await page.getByRole("button", { name: "Save changes" }).click();
  const dialog = page.getByRole("dialog");
  await dialog.getByLabel("Change note").fill("wall type matters less (e2e)");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();
  await expect(header).not.toHaveText(before ?? "");

  await page.getByRole("link", { name: "Audit" }).click();
  await expect(page.getByRole("row", { name: /template edited/ })).toBeVisible();
});

test("a new supplier user is deactivated and reactivated", async ({ browser }) => {
  const operator = await (await browser.newContext()).newPage();
  await signIn(operator, "ops@sanovio-demo.example");
  await operator.getByRole("link", { name: "Accounts" }).click();
  await operator.getByRole("button", { name: "New user" }).click();
  const dialog = operator.getByRole("dialog");
  await dialog.getByLabel(/Organization/).selectOption({ label: "BD (supplier)" });
  await dialog.getByLabel("Email").fill("e2e.user@bd-demo.example");
  await dialog.getByLabel("Name", { exact: true }).fill("E2E User");
  await dialog.getByLabel(/^Password/).fill("sechs6");
  await dialog.getByRole("button", { name: "Save" }).click();
  await expect(dialog).toBeHidden();

  const user = operator.getByRole("row", { name: /e2e.user@bd-demo.example/ });
  await user.getByRole("button", { name: "Deactivate" }).click();
  await expect(user.getByText("deactivated")).toBeVisible();

  const supplier = await (await browser.newContext()).newPage();
  await signIn(supplier, "e2e.user@bd-demo.example", "sechs6");
  await expect(supplier.getByRole("alert")).toContainText("invalid email or password");

  await user.getByRole("button", { name: "Reactivate" }).click();
  await expect(user.getByText("active", { exact: true })).toBeVisible();
  await supplier.getByRole("button", { name: "Sign in" }).click();
  await expect(supplier.getByRole("link", { name: "Requests" })).toBeVisible();
});
