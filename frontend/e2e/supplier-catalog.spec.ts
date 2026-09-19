import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "e2e-demo-password";
const HUB_APP = "http://127.0.0.1:15174";
const FAMILY = "BD Luer-Lok™ Spritze 20 ml (e2e)";

async function signIn(page: Page, email: string) {
  await page.goto(HUB_APP);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
}

// A family of its own, so the seeded catalog scenario 1 relies on stays as it is.
test("a supplier adds a family and a variant, then retires it", async ({ browser }) => {
  const bd = await (await browser.newContext()).newPage();
  await signIn(bd, "catalog@bd-demo.example");
  await bd.getByRole("link", { name: "Catalog" }).click();
  await bd.getByRole("button", { name: "New family" }).click();
  const family = bd.getByRole("dialog");
  await family.getByLabel("Category").selectOption("syringe_single_use");
  await family.getByLabel("Name", { exact: true }).fill(FAMILY);
  await family.getByLabel("Description").fill("Luer-Lock-Ansatz, zentrisch.");
  await family.getByRole("button", { name: "Save" }).click();
  await expect(bd.getByRole("heading", { name: FAMILY })).toBeVisible();

  await bd.getByRole("button", { name: "Add variant" }).click();
  const row = bd.getByRole("dialog");
  await row.getByLabel("Article no.").fill("300999");
  await row.getByLabel("Label").fill("BD Luer-Lok™ 20 ml");
  await row.getByLabel(/^Size/).fill("20 ml");
  await row.getByLabel("GTIN").fill("4006381333931");
  await row.getByRole("button", { name: "Add" }).click();
  await expect(row).toBeHidden();
  const variant = bd.locator("section").filter({ hasText: "One variant" });
  await expect(variant.getByRole("row", { name: /Nominal volume/ })).toContainText("20");

  await variant.getByRole("button", { name: "Retire" }).click();
  await expect(variant.getByRole("button", { name: "Reactivate" })).toBeVisible();

  const operator = await (await browser.newContext()).newPage();
  await signIn(operator, "ops@sanovio-demo.example");
  await operator.getByRole("link", { name: "Catalog" }).click();
  await expect(operator.getByRole("link", { name: FAMILY })).toBeVisible();
});
