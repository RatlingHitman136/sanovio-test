import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import {
  HUB,
  NODE,
  article,
  articleSummary,
  injektAttributes,
  preview,
  requirement,
  searchResponse,
} from "../test/fixtures";
import { renderPurchaser, serve } from "../test/harness";

test("the article list shows categories and data-quality warnings", async () => {
  const queries: (string | null)[] = [];
  serve(
    http.get(`${NODE}/api/v1/articles`, ({ request }) => {
      queries.push(new URL(request.url).searchParams.get("q"));
      return HttpResponse.json([articleSummary]);
    }),
  );
  await renderPurchaser("/articles");

  expect(await screen.findByRole("link", { name: articleSummary.name })).toBeInTheDocument();
  expect(screen.getByText("GTIN_EAN_MISMATCH")).toBeInTheDocument();

  await userEvent.type(screen.getByLabelText("Filter articles"), "Spritze");
  await waitFor(() => {
    expect(queries).toContain("Spritze");
  });
});

function articleHandlers(searches: unknown[]) {
  return [
    http.get(`${NODE}/api/v1/articles/art-3`, () => HttpResponse.json(article)),
    http.post(`${NODE}/api/v1/articles/art-3/requirement`, () =>
      HttpResponse.json({ requirement, egress_id: "e1" }),
    ),
    http.post(`${HUB}/api/v1/search`, async ({ request }) => {
      searches.push(await request.json());
      return HttpResponse.json(searchResponse(searches.length));
    }),
  ];
}

test("a search shows what leaves the hospital and the candidates", async () => {
  const searches: unknown[] = [];
  serve(...articleHandlers(searches));
  await renderPurchaser("/articles/art-3");

  await userEvent.click(await screen.findByRole("button", { name: "Search the hub" }));

  expect(await screen.findByText("Injekt® Luer Lock Solo 10 ml (4606728V)")).toBeInTheDocument();
  expect(screen.getByText("What leaves the hospital")).toBeInTheDocument();
  // Hospital-only data is on the page, and not in what was sent.
  expect(screen.getByText("0.12 CHF")).toBeInTheDocument();
  expect(JSON.stringify(searches)).not.toContain("0.12");
  expect(JSON.stringify(searches)).not.toContain(article.name);
});

test("starting an assessment sends the requirement and opens it", async () => {
  const searches: unknown[] = [];
  const opened: unknown[] = [];
  serve(
    ...articleHandlers(searches),
    http.post(`${HUB}/api/v1/assessments`, async ({ request }) => {
      opened.push(await request.json());
      return HttpResponse.json({ id: "asm-1", status: "ASSESSING" }, { status: 202 });
    }),
  );
  const { router } = await renderPurchaser("/articles/art-3");
  await userEvent.click(await screen.findByRole("button", { name: "Search the hub" }));
  const row = (await screen.findByText("BD Plastipak™ Luer-Lok™ 10 ml (300912)")).closest("tr");
  if (!row) throw new Error("no candidate row");

  await userEvent.click(within(row).getByRole("button", { name: "Start assessment" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Start assessment" }));

  await waitFor(() => {
    expect(router.state.location.pathname).toBe("/assessments/asm-1");
  });
  expect(opened).toEqual([{ requirement, variant_id: "var-plastipak" }]);
});

test("an assessment already open for the pair is opened instead", async () => {
  serve(
    ...articleHandlers([]),
    http.post(`${HUB}/api/v1/assessments`, () =>
      HttpResponse.json(
        { detail: "already open", code: "ASSESSMENT_OPEN", assessment_id: "asm-9" },
        { status: 409 },
      ),
    ),
  );
  const { router } = await renderPurchaser("/articles/art-3");
  await userEvent.click(await screen.findByRole("button", { name: "Search the hub" }));
  const row = (await screen.findByText("BD Plastipak™ Luer-Lok™ 10 ml (300912)")).closest("tr");
  if (!row) throw new Error("no candidate row");

  await userEvent.click(within(row).getByRole("button", { name: "Start assessment" }));
  await userEvent.click(
    within(await screen.findByRole("dialog")).getByRole("button", { name: "Start assessment" }),
  );

  await waitFor(() => {
    expect(router.state.location.pathname).toBe("/assessments/asm-9");
  });
});

test("marking the current product needs a choice per conflict, then searches again", async () => {
  const searches: unknown[] = [];
  const linked: unknown[] = [];
  serve(
    ...articleHandlers(searches),
    http.get(`${HUB}/api/v1/catalog/variants/var-injekt/attributes`, () =>
      HttpResponse.json(injektAttributes),
    ),
    http.post(`${NODE}/api/v1/articles/art-3/reference/preview`, () => HttpResponse.json(preview)),
    http.put(`${NODE}/api/v1/articles/art-3/reference`, async ({ request }) => {
      linked.push(await request.json());
      return HttpResponse.json(article);
    }),
  );
  await renderPurchaser("/articles/art-3");
  await userEvent.click(await screen.findByRole("button", { name: "Search the hub" }));
  const row = (await screen.findByText("Injekt® Luer Lock Solo 10 ml (4606728V)")).closest("tr");
  if (!row) throw new Error("no candidate row");

  await userEvent.click(within(row).getByRole("button", { name: "This is our current product" }));
  const dialog = await screen.findByRole("dialog");
  const confirm = within(dialog).getByRole("button", { name: "Mark and search again" });
  await waitFor(() => {
    expect(within(dialog).getByText("Filled in (1)")).toBeInTheDocument();
  });
  expect(confirm).toBeDisabled();

  await userEvent.selectOptions(within(dialog).getByLabelText("Choice for design"), "KEEP_OURS");
  await userEvent.click(confirm);

  await waitFor(() => {
    expect(searches).toHaveLength(2);
  });
  expect(linked).toEqual([
    {
      variant_id: "var-injekt",
      label: injektAttributes.label,
      attributes: injektAttributes.attributes,
      conflict_choices: { design: "KEEP_OURS" },
    },
  ]);
});

test("an unknown attribute is entered with the input its template asks for", async () => {
  const saved: unknown[] = [];
  serve(
    ...articleHandlers([]),
    http.put(`${NODE}/api/v1/articles/art-3/facts/connector`, async ({ request }) => {
      saved.push(await request.json());
      return HttpResponse.json(article);
    }),
  );
  await renderPurchaser("/articles/art-3");
  const row = (await screen.findByText("Connector")).closest("tr");
  if (!row) throw new Error("no attribute row");

  await userEvent.click(within(row).getByRole("button", { name: "Enter" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.selectOptions(within(dialog).getByLabelText("Connector"), "LUER_LOCK");
  await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() => {
    expect(saved).toEqual([{ cannot_provide: false, value: { type: "enum", value: "LUER_LOCK" } }]);
  });
});
