import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "e2e-demo-password";
const PURCHASER = "http://127.0.0.1:15173";
const SUPPLIER = "http://127.0.0.1:15174";

// What Anna knows about art_03 that its name does not say (as the CLI demo's scenario 1).
const KNOWLEDGE: Record<string, { select?: string; type?: string }> = {
  single_use: { select: "yes" },
  standards: { type: "ISO 7886-1" },
  special_scale: { type: "keine" },
  needle_included: { select: "no" },
  safety_mechanism: { select: "no" },
  pump_compatible: { select: "no" },
  light_protected: { select: "no" },
};

async function signIn(page: Page, url: string, email: string) {
  await page.goto(url);
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function answerWhatWeKnow(page: Page) {
  const questions = page.locator("li[data-attribute-key]");
  const count = await questions.count();
  for (let index = 0; index < count; index++) {
    const question = questions.nth(index);
    const key = (await question.getAttribute("data-attribute-key")) ?? "";
    const known = KNOWLEDGE[key];
    if (!known) continue;
    if (known.select) await question.getByRole("combobox").selectOption({ label: known.select });
    if (known.type) await question.getByRole("textbox").fill(known.type);
  }
  await page.getByRole("button", { name: /^Save \d+ answers?$/ }).click();
}

test("scenario 1: search, current product, assessment, answers, verdict", async ({ browser }) => {
  const purchaser = await (await browser.newContext()).newPage();
  await signIn(purchaser, PURCHASER, "anna.meier@demo-ksp.example");
  await purchaser.getByRole("link", { name: "Articles" }).click();
  await purchaser.getByRole("link", { name: "Einmalspritze 10 ml Luer-Lock steril" }).click();

  // First search on what the name says; Injekt is the product the hospital buys today.
  await purchaser.getByRole("button", { name: "Search the hub" }).click();
  const injekt = purchaser.getByRole("row", { name: /Injekt® Luer Lock Solo 10 ml/ });
  await injekt.getByRole("button", { name: "This is our current product" }).click();
  const dialog = purchaser.getByRole("dialog");
  await expect(dialog.getByText(/Filled in/)).toBeVisible();
  for (const choice of await dialog.getByRole("combobox").all()) {
    await choice.selectOption("KEEP_OURS");
  }
  await dialog.getByRole("button", { name: "Mark and search again" }).click();
  await expect(dialog).toBeHidden();
  const current = purchaser.locator("section").filter({
    has: purchaser.getByRole("heading", { name: "Current product", exact: true }),
  });
  await expect(current).toContainText("Injekt® Luer Lock Solo 10 ml");

  // The assessment against BD Plastipak; the requirement is shown before it leaves.
  const plastipak = purchaser.getByRole("row", { name: /BD Plastipak™ Luer-Lok™ 10 ml/ });
  await plastipak.getByRole("button", { name: "Start assessment" }).click();
  const start = purchaser.getByRole("dialog");
  await expect(start.getByText("What leaves the hospital")).toBeVisible();
  await start.getByRole("button", { name: "Start assessment" }).click();
  await expect(purchaser.getByText("needs question review").first()).toBeVisible();

  await answerWhatWeKnow(purchaser);
  await expect(purchaser.getByText("Questions for you")).toBeHidden();
  await purchaser.getByRole("button", { name: "Send questions" }).click();
  await expect(purchaser.getByText("Waiting for BD to answer.")).toBeVisible();

  // BD answers in its own app (the development simulator stands in for the catalog team).
  const supplier = await (await browser.newContext()).newPage();
  await signIn(supplier, SUPPLIER, "catalog@bd-demo.example");
  await expect(supplier.getByRole("cell", { name: "Hospital H-7F3A" })).toBeVisible();
  await supplier.getByRole("link", { name: /BD Plastipak™ Luer-Lok™ 10 ml/ }).click();
  await supplier.getByRole("button", { name: "Let the simulator answer (dev)" }).click();
  await expect(supplier.getByText("Nothing is waiting for an answer.")).toBeVisible();

  // Round 2 arrives on the purchaser's open page by polling; she confirms it.
  await expect(purchaser.getByText("proposed resolution").first()).toBeVisible({ timeout: 60_000 });
  await expect(purchaser.getByText("Verdict · round 2")).toBeVisible();
  await purchaser.getByRole("button", { name: "Confirm verdict" }).click();
  await purchaser.getByRole("dialog").getByRole("button", { name: "Resolve" }).click();
  await expect(purchaser.getByText("resolved", { exact: true }).first()).toBeVisible();
  await expect(purchaser.getByText("equivalent with deviations").first()).toBeVisible();
});
