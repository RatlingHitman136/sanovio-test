import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { family } from "../test/fixtures";
import { HUB, renderSupplier, serve } from "../test/harness";

function familyHandlers(puts: unknown[], deletes: string[]) {
  return [
    http.get(`${HUB}/api/v1/supplier/catalog/families/fam-1`, () => HttpResponse.json(family)),
    http.put(`${HUB}/api/v1/supplier/catalog/facts`, async ({ request }) => {
      puts.push(await request.json());
      return HttpResponse.json({
        fact_id: "n1",
        attribute_key: "x",
        variant_id: null,
        value: null,
        unavailable: false,
      });
    }),
    http.delete(`${HUB}/api/v1/supplier/catalog/facts/:factId`, ({ params }) => {
      deletes.push(String(params.factId));
      return new HttpResponse(null, { status: 204 });
    }),
  ];
}

function tableOf(title: string): HTMLElement {
  const card = screen.getByText(title).closest("section");
  if (!card) throw new Error(`no card ${title}`);
  return card;
}

test("a family value is set for every variant", async () => {
  const puts: unknown[] = [];
  serve(...familyHandlers(puts, []));
  await renderSupplier("/catalog/fam-1");

  const familyCard = await waitFor(() => tableOf("For the whole family"));
  const row = within(familyCard).getByText("Special scale").closest("tr");
  if (!row) throw new Error("no row");
  await userEvent.click(within(row).getByRole("button", { name: "Edit" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.type(within(dialog).getByLabelText("Special scale"), "keine");
  await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() => {
    expect(puts).toEqual([
      {
        family_id: "fam-1",
        variant_id: null,
        attribute_key: "special_scale",
        value: { type: "text", value: "keine" },
        unavailable: false,
      },
    ]);
  });
});

test("a variant override is marked as such and can be removed", async () => {
  const puts: unknown[] = [];
  const deletes: string[] = [];
  serve(...familyHandlers(puts, deletes));
  await renderSupplier("/catalog/fam-1");

  const variantCard = await waitFor(() => tableOf("One variant"));
  const row = within(variantCard).getByText("Special scale").closest("tr");
  if (!row) throw new Error("no row");
  expect(within(row).getByText("this variant")).toBeInTheDocument();
  expect(within(row).getByText("set by us")).toBeInTheDocument();

  await userEvent.click(within(row).getByRole("button", { name: "Remove override" }));
  await waitFor(() => {
    expect(deletes).toEqual(["o1"]);
  });
});

test("a variant can be marked as not available", async () => {
  const puts: unknown[] = [];
  serve(...familyHandlers(puts, []));
  await renderSupplier("/catalog/fam-1");

  const variantCard = await waitFor(() => tableOf("One variant"));
  const row = within(variantCard).getByText("DEHP-free").closest("tr");
  if (!row) throw new Error("no row");
  await userEvent.click(within(row).getByRole("button", { name: "Override" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.click(within(dialog).getByLabelText("Not available for this product"));
  await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() => {
    expect(puts).toEqual([
      {
        family_id: null,
        variant_id: "var-10",
        attribute_key: "dehp_free",
        value: null,
        unavailable: true,
      },
    ]);
  });
});
