import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import {
  HUB,
  NODE,
  article,
  articleSummary,
  assessment,
  colleagues,
  purchaserDraft,
  requirement,
  summaryOf,
  supplierDraft,
} from "../test/fixtures";
import { renderPurchaser, serve } from "../test/harness";

function assessmentHandlers(detail: ReturnType<typeof assessment>, variantGtin?: string) {
  return [
    http.get(`${HUB}/api/v1/assessments/asm-1`, () => HttpResponse.json(detail)),
    http.get(`${NODE}/api/v1/articles`, () => HttpResponse.json([articleSummary])),
    http.get(`${NODE}/api/v1/articles/art-3`, () => HttpResponse.json(article)),
    http.get(`${NODE}/api/v1/users`, () => HttpResponse.json(colleagues)),
    http.get(`${HUB}/api/v1/catalog/variants/var-plastipak/attributes`, () =>
      HttpResponse.json({
        variant_id: "var-plastipak",
        label: detail.variant_label,
        attributes: {},
        identifiers: variantGtin
          ? [{ scheme: "GTIN", value: variantGtin, checksum_valid: true, fact_id: "i1" }]
          : [],
        additional_information: {},
      }),
    ),
  ];
}

test("the list joins our article names and colleagues in the browser", async () => {
  const detail = assessment();
  let hubQuery = "";
  serve(
    ...assessmentHandlers(detail),
    http.get(`${HUB}/api/v1/assessments`, ({ request }) => {
      hubQuery = new URL(request.url).search;
      return HttpResponse.json([summaryOf(detail)]);
    }),
  );
  await renderPurchaser("/");

  expect(await screen.findByText(articleSummary.name)).toBeInTheDocument();
  expect(await screen.findByText("Beat Keller")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: detail.variant_label })).toHaveAttribute(
    "href",
    "/assessments/asm-1",
  );

  await userEvent.click(screen.getByLabelText("Assigned to me"));
  await waitFor(() => {
    expect(hubQuery).toBe("?assigned_to=me");
  });
});

test("the comparison shows both sides, the judgment and the weight", async () => {
  serve(...assessmentHandlers(assessment()));
  await renderPurchaser("/assessments/asm-1");

  const row = (await screen.findByText("Design")).closest("tr");
  if (!row) throw new Error("no design row");
  expect(within(row).getByText("TWO_PART")).toBeInTheDocument();
  expect(within(row).getByText("THREE_PART")).toBeInTheDocument();
  expect(within(row).getByText("mismatch")).toBeInTheDocument();
  expect(within(row).getByText("major")).toBeInTheDocument();
  expect(screen.getByText("Blocking information is missing.")).toBeInTheDocument();
});

test("our answer is saved at the node and reaches the hub only inside a requirement", async () => {
  const facts: unknown[] = [];
  const requirements: unknown[] = [];
  const answered: unknown[] = [];
  serve(
    ...assessmentHandlers(assessment()),
    http.put(`${NODE}/api/v1/articles/art-3/facts/connector`, async ({ request }) => {
      facts.push(await request.json());
      return HttpResponse.json(article);
    }),
    http.post(`${NODE}/api/v1/articles/art-3/requirement`, async ({ request }) => {
      requirements.push(await request.json());
      return HttpResponse.json({ requirement, egress_id: "e2" });
    }),
    http.post(`${HUB}/api/v1/assessments/asm-1/requirements`, async ({ request }) => {
      answered.push(await request.json());
      return HttpResponse.json(summaryOf(assessment()));
    }),
  );
  await renderPurchaser("/assessments/asm-1");

  await userEvent.selectOptions(await screen.findByLabelText(purchaserDraft.text), "LUER_LOCK");
  await userEvent.click(screen.getByRole("button", { name: "Save 1 answer" }));

  await waitFor(() => {
    expect(answered).toEqual([{ requirement, version: 4 }]);
  });
  expect(facts).toEqual([
    {
      cannot_provide: false,
      value: { type: "enum", value: "LUER_LOCK" },
      hub_question_id: "q-purchaser",
    },
  ]);
  expect(requirements).toEqual([{ answered_question_ids: ["q-purchaser"] }]);
});

test("questions are sent only when we owe nothing, and a pending proposal is explained", async () => {
  const sent: unknown[] = [];
  serve(
    ...assessmentHandlers(assessment({ questions: [supplierDraft] })),
    http.post(`${HUB}/api/v1/assessments/asm-1/send-questions`, async ({ request }) => {
      sent.push(await request.json());
      return HttpResponse.json(
        { detail: "attribute proposals are still running", code: "ATTRIBUTE_PROPOSAL_PENDING" },
        { status: 409 },
      );
    }),
  );
  await renderPurchaser("/assessments/asm-1");

  await userEvent.click(await screen.findByRole("button", { name: "Send questions" }));

  expect(await screen.findByText(/still being matched to attributes/)).toBeInTheDocument();
  expect(sent).toEqual([{ version: 4 }]);
});

test("sending waits while our own questions are open", async () => {
  serve(...assessmentHandlers(assessment()));
  await renderPurchaser("/assessments/asm-1");

  expect(await screen.findByRole("button", { name: "Send questions" })).toBeDisabled();
  expect(screen.getByText("Answer or withdraw your questions first.")).toBeInTheDocument();
});

test("a proposed verdict is confirmed as it stands", async () => {
  const resolved: unknown[] = [];
  serve(
    ...assessmentHandlers(
      assessment({
        status: "PROPOSED_RESOLUTION",
        proposed_verdict: "EQUIVALENT_WITH_DEVIATIONS",
        questions: [],
      }),
    ),
    http.post(`${HUB}/api/v1/assessments/asm-1/resolve`, async ({ request }) => {
      resolved.push(await request.json());
      return HttpResponse.json(summaryOf(assessment({ status: "RESOLVED" })));
    }),
  );
  await renderPurchaser("/assessments/asm-1");

  await userEvent.click(await screen.findByRole("button", { name: "Confirm verdict" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Resolve" }));

  await waitFor(() => {
    expect(resolved).toEqual([{ verdict: "EQUIVALENT_WITH_DEVIATIONS", note: null, version: 4 }]);
  });
});

test("an override needs a note", async () => {
  serve(
    ...assessmentHandlers(
      assessment({ status: "PROPOSED_RESOLUTION", proposed_verdict: "EQUIVALENT", questions: [] }),
    ),
  );
  await renderPurchaser("/assessments/asm-1");

  await userEvent.click(await screen.findByRole("button", { name: "Override" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.selectOptions(within(dialog).getByLabelText("Verdict"), "NOT_EQUIVALENT");

  expect(within(dialog).getByRole("button", { name: "Resolve" })).toBeDisabled();
  await userEvent.type(within(dialog).getByLabelText(/Note/), "Clinicians prefer 2-part.");
  expect(within(dialog).getByRole("button", { name: "Resolve" })).toBeEnabled();
});

test("a valid GTIN on both sides shows the same-trade-item banner", async () => {
  const ours = {
    ...article,
    identifiers: [{ scheme: "GTIN", value: "04040456789018", checksum_valid: true }],
  };
  // The first matching handler answers, so the override comes first.
  serve(
    http.get(`${NODE}/api/v1/articles/art-3`, () => HttpResponse.json(ours)),
    ...assessmentHandlers(assessment(), "04040456789018"),
  );
  await renderPurchaser("/assessments/asm-1");

  expect(await screen.findByText(/Same trade item: GTIN 04040456789018/)).toBeInTheDocument();
});

test("the comparison sorts by criticality and filters by judgment", async () => {
  serve(...assessmentHandlers(assessment()));
  await renderPurchaser("/assessments/asm-1");

  const table = (await screen.findByText("Design")).closest("table");
  if (!table) throw new Error("no comparison table");
  const names = () =>
    within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => row.querySelector("td")?.textContent);
  // Critical before major by default; by judgment, the mismatch comes first.
  expect(names()).toEqual(["Nominal volume", "Design"]);
  await userEvent.selectOptions(screen.getByLabelText("Sort by"), "judgment");
  expect(names()).toEqual(["Design", "Nominal volume"]);
  expect(screen.getByRole("button", { name: "mismatch 1" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "mismatch 1" }));
  expect(names()).toEqual(["Design"]);

  await userEvent.click(screen.getByRole("button", { name: "match 1" }));
  expect(names()).toEqual(["Nominal volume"]);

  await userEvent.click(screen.getByLabelText("decided by model"));
  expect(screen.getByText("Nothing matches this filter.")).toBeInTheDocument();
});
