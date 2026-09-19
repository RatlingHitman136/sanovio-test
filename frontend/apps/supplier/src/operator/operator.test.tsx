import type { HubSchemas } from "@sanovio/api";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { family } from "../test/fixtures";
import { HUB, renderOperator, renderSupplier, serve } from "../test/harness";

type Proposal = HubSchemas["schemas"]["AttributeProposalView"];
type Job = HubSchemas["schemas"]["JobView"];

const proposal: Proposal = {
  id: "prop-1",
  question_id: "q-1",
  question_text: "Liegt der Packung ein abziehbares Dokumentationsetikett bei?",
  category_code: "syringe_single_use",
  result: "NEW",
  status: "PROVISIONAL",
  proposal: {
    key: "peel_off_label",
    type: "bool",
    unit: null,
    options: [],
    labels: { de: "Abziehbares Dokumentationsetikett", en: "Peel-off documentation label" },
  },
  attribute_key: "peel_off_label",
  identifier_key: null,
  review_note: null,
  value_count: 1,
  created_at: "2026-09-19T08:00:00Z",
};

const attribute = (key: string, value_type: string) => ({
  key,
  kind: "ATTRIBUTE",
  value_type,
  unit: null,
  options: null,
  labels: { en: key },
  status: "APPROVED",
  origin: "SEED",
});

/** The table row showing `text`; filters and menus may show the same words. */
function row(text: string): HTMLElement {
  const found = screen
    .getAllByText(text)
    .map((element) => element.closest("tr"))
    .find((element) => element !== null);
  if (!found) throw new Error(`no row ${text}`);
  return found;
}

function proposals(posts: { url: string; body: unknown }[]) {
  return [
    http.get(`${HUB}/api/v1/admin/attribute-proposals`, () => HttpResponse.json([proposal])),
    http.get(`${HUB}/api/v1/attributes`, () =>
      HttpResponse.json([
        attribute("latex_free", "bool"),
        attribute("nominal_volume_ml", "number"),
      ]),
    ),
    http.post(`${HUB}/api/v1/admin/attribute-proposals/prop-1/:action`, async ({ request }) => {
      posts.push({ url: new URL(request.url).pathname, body: await request.json() });
      if (request.url.endsWith("/merge")) {
        return HttpResponse.json({ detail: "latex_free cannot hold: WITH_LABEL" }, { status: 422 });
      }
      return HttpResponse.json({ ...proposal, status: "APPROVED" });
    }),
  ];
}

test("an operator gets the console and never the supplier's inbox", async () => {
  serve(
    http.get(`${HUB}/api/v1/admin/attribute-proposals`, () => HttpResponse.json([proposal])),
    http.get(`${HUB}/api/v1/admin/jobs`, () => HttpResponse.json([])),
    http.get(`${HUB}/api/v1/admin/llm-usage`, () => HttpResponse.json([])),
    http.get(`${HUB}/api/v1/admin/stats/assessments`, () =>
      HttpResponse.json([
        { tenant_code: "ten_ksp", by_status: { ASSESSING: 2 }, by_verdict: { EQUIVALENT: 1 } },
      ]),
    ),
  );
  await renderOperator("/");

  expect(await screen.findByRole("heading", { name: "Overview" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Curation" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Requests" })).not.toBeInTheDocument();
  expect(await screen.findByText("ten_ksp")).toBeInTheDocument();
});

test("a supplier never sees an operator page", async () => {
  serve(http.get(`${HUB}/api/v1/supplier/requests`, () => HttpResponse.json([])));
  await renderSupplier("/");

  expect(await screen.findByRole("link", { name: "Requests" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Curation" })).not.toBeInTheDocument();
});

test("approving sets criticality and rule, with the labels as proposed", async () => {
  const posts: { url: string; body: unknown }[] = [];
  serve(...proposals(posts));
  await renderOperator("/proposals");

  await userEvent.click(
    await within(await waitFor(() => row(proposal.question_text))).findByRole("button", {
      name: "Approve",
    }),
  );
  const dialog = await screen.findByRole("dialog");
  await userEvent.selectOptions(within(dialog).getByLabelText("Criticality"), "minor");
  await userEvent.click(within(dialog).getByRole("button", { name: "Approve" }));

  await waitFor(() => {
    expect(posts).toEqual([
      {
        url: "/api/v1/admin/attribute-proposals/prop-1/approve",
        body: {
          criticality: "minor",
          rule: "exact",
          tolerance: null,
          shareable: true,
          labels: { de: "Abziehbares Dokumentationsetikett", en: "Peel-off documentation label" },
        },
      },
    ]);
  });
});

test("a merge offers only attributes of the same type and shows why it was refused", async () => {
  const posts: { url: string; body: unknown }[] = [];
  serve(...proposals(posts));
  await renderOperator("/proposals");

  await userEvent.click(
    await within(await waitFor(() => row(proposal.question_text))).findByRole("button", {
      name: "Merge",
    }),
  );
  const dialog = await screen.findByRole("dialog");
  const target = within(dialog).getByLabelText("Merge into");
  await waitFor(() => {
    expect(within(target).getByRole("option", { name: /latex_free/ })).toBeInTheDocument();
  });
  expect(within(target).queryByRole("option", { name: /nominal_volume_ml/ })).toBeNull();
  await userEvent.selectOptions(target, "latex_free");
  await userEvent.type(within(dialog).getByLabelText("Note"), "asked the same");
  await userEvent.click(within(dialog).getByRole("button", { name: "Merge" }));

  expect(await within(dialog).findByRole("alert")).toHaveTextContent("latex_free cannot hold");
  expect(posts[0]?.body).toEqual({ attribute_key: "latex_free", note: "asked the same" });
});

test("a template change is saved with its change note", async () => {
  const patches: unknown[] = [];
  const template = {
    code: "syringe_single_use",
    definition: {
      attributes: [
        {
          key: "special_scale",
          type: "text",
          labels: { en: "Special scale" },
          criticality: "major",
          rule: "exact",
          tolerance: null,
          shareable: true,
        },
      ],
    },
    definition_hash: "a".repeat(64),
    change_note: "Seed",
    updated_at: "2026-09-19T08:00:00Z",
  };
  serve(
    http.get(`${HUB}/api/v1/templates/syringe_single_use`, () => HttpResponse.json(template)),
    http.get(`${HUB}/api/v1/attributes`, () => HttpResponse.json([])),
    http.patch(`${HUB}/api/v1/admin/templates/syringe_single_use`, async ({ request }) => {
      patches.push(await request.json());
      return HttpResponse.json(template);
    }),
  );
  await renderOperator("/templates/syringe_single_use");

  await userEvent.selectOptions(await screen.findByLabelText("special_scale criticality"), "minor");
  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("Change note"), "matters less");
  await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() => {
    expect(patches).toEqual([
      {
        set: {
          special_scale: { criticality: "minor", rule: "exact", tolerance: null, shareable: true },
        },
        add: {},
        remove: [],
        change_note: "matters less",
      },
    ]);
  });
});

test("a password reset is sent for the chosen user", async () => {
  const resets: unknown[] = [];
  serve(
    http.get(`${HUB}/api/v1/admin/organizations`, () =>
      HttpResponse.json([{ id: "org-bd", code: "org_bd", name: "BD", type: "SUPPLIER" }]),
    ),
    http.get(`${HUB}/api/v1/admin/users`, () =>
      HttpResponse.json([
        {
          id: "u-1",
          org_id: "org-bd",
          organization: "BD",
          email: "catalog@bd-demo.example",
          display_name: "BD Catalog",
          role: "SUPPLIER",
          is_active: true,
        },
      ]),
    ),
    http.post(`${HUB}/api/v1/admin/users/u-1/password`, async ({ request }) => {
      resets.push(await request.json());
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await renderOperator("/accounts");

  await userEvent.click(
    within(await waitFor(() => row("catalog@bd-demo.example"))).getByRole("button", {
      name: "Reset password",
    }),
  );
  const dialog = await screen.findByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("New password"), "neues-pw");
  await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() => {
    expect(resets).toEqual([{ password: "neues-pw" }]);
  });
});

test("only a job outside an assessment can be retried here", async () => {
  const retried: string[] = [];
  const job = (id: string, kind: Job["kind"], retryable: boolean): Job => ({
    id,
    kind,
    status: "FAILED",
    payload: {},
    attempts: 3,
    max_attempts: 3,
    run_after: "2026-09-19T08:00:00Z",
    finished_at: "2026-09-19T08:01:00Z",
    last_error: "RuntimeError",
    retryable,
  });
  serve(
    http.get(`${HUB}/api/v1/admin/jobs`, () =>
      HttpResponse.json([job("j-1", "ASSESS", false), job("j-2", "NORMALIZE_ITEM", true)]),
    ),
    http.post(`${HUB}/api/v1/admin/jobs/:id/retry`, ({ params }) => {
      retried.push(String(params.id));
      return HttpResponse.json(job(String(params.id), "NORMALIZE_ITEM", false));
    }),
  );
  await renderOperator("/jobs");

  const assess = await waitFor(() => row("assess"));
  expect(within(assess).queryByRole("button", { name: "Retry" })).toBeNull();
  expect(within(assess).getByText(/retried by the hospital/)).toBeInTheDocument();
  await userEvent.click(within(row("normalize_item")).getByRole("button", { name: "Retry" }));
  await waitFor(() => {
    expect(retried).toEqual(["j-2"]);
  });
});

test("an operator reads a supplier's family but cannot edit it", async () => {
  const reread: string[] = [];
  serve(
    http.get(`${HUB}/api/v1/admin/catalog/families/fam-1`, () => HttpResponse.json(family)),
    http.post(`${HUB}/api/v1/admin/catalog/families/fam-1/normalize`, () => {
      reread.push("fam-1");
      return HttpResponse.json({});
    }),
  );
  await renderOperator("/catalog/fam-1");

  expect(await screen.findByText("For the whole family")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Edit" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Override" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Remove override" })).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Re-read catalog data" }));
  await waitFor(() => {
    expect(reread).toEqual(["fam-1"]);
  });
});
