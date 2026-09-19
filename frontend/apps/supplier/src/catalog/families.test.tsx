import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { family } from "../test/fixtures";
import { HUB, renderOperator, renderSupplier, serve } from "../test/harness";

const templates = [
  {
    code: "syringe_single_use",
    definition: {},
    definition_hash: "a",
    change_note: null,
    updated_at: "",
  },
];

function familyHandlers(posts: { url: string; body: unknown }[], detail = family) {
  const record = async ({ request }: { request: Request }) => {
    posts.push({
      url: new URL(request.url).pathname,
      body: await request.json().catch(() => null),
    });
    return HttpResponse.json(detail);
  };
  return [
    http.get(`${HUB}/api/v1/supplier/catalog`, () => HttpResponse.json([])),
    http.get(`${HUB}/api/v1/templates`, () => HttpResponse.json(templates)),
    http.get(`${HUB}/api/v1/supplier/catalog/families/fam-1`, () => HttpResponse.json(detail)),
    http.post(`${HUB}/api/v1/supplier/catalog/families`, record),
    http.post(`${HUB}/api/v1/supplier/catalog/families/fam-1/variants`, record),
    http.post(`${HUB}/api/v1/supplier/catalog/variants/:id/:action`, record),
  ];
}

test("a new family is created in its category and opened", async () => {
  const posts: { url: string; body: unknown }[] = [];
  serve(...familyHandlers(posts));
  const router = await renderSupplier("/catalog");

  await userEvent.click(await screen.findByRole("button", { name: "New family" }));
  const dialog = await screen.findByRole("dialog");
  await waitFor(() => {
    expect(within(dialog).getByRole("option", { name: "syringe_single_use" })).toBeInTheDocument();
  });
  await userEvent.selectOptions(within(dialog).getByLabelText("Category"), "syringe_single_use");
  await userEvent.type(within(dialog).getByLabelText("Name"), "BD Luer-Lok 20 ml");
  await userEvent.type(within(dialog).getByLabelText("Description"), "Luer-Lock, zentrisch");
  await userEvent.click(within(dialog).getByRole("button", { name: "Save" }));

  await waitFor(() => {
    expect(router.state.location.pathname).toBe("/catalog/fam-1");
  });
  expect(posts).toEqual([
    {
      url: "/api/v1/supplier/catalog/families",
      body: {
        name: "BD Luer-Lok 20 ml",
        manufacturer: "BD",
        brand_name: null,
        product_type: null,
        description: "Luer-Lock, zentrisch",
        properties_text: null,
        category_code: "syringe_single_use",
      },
    },
  ]);
});

test("a variant copied from a sibling keeps the row but not the article's numbers", async () => {
  const posts: { url: string; body: unknown }[] = [];
  serve(...familyHandlers(posts));
  await renderSupplier("/catalog/fam-1");

  await userEvent.click(await screen.findByRole("button", { name: "Add variant" }));
  const dialog = await screen.findByRole("dialog");
  await userEvent.selectOptions(within(dialog).getByLabelText("Copy from"), "var-10");
  expect(within(dialog).getByLabelText("Article no.")).toHaveValue("");
  await userEvent.type(within(dialog).getByLabelText("Article no."), "300999");
  await userEvent.type(within(dialog).getByLabelText("GTIN"), "4006381333931");
  await userEvent.click(within(dialog).getByRole("button", { name: "Add" }));

  await waitFor(() => {
    expect(posts).toEqual([
      {
        url: "/api/v1/supplier/catalog/families/fam-1/variants",
        body: {
          article_no: "300999",
          label: "BD Plastipak™ Luer-Lok™ 10 ml",
          size_text: "10 ml",
          order_unit: "Box",
          units_per_order_unit: 100,
          order_units_per_shipping_unit: 8,
          gtin: "4006381333931",
          pzn: null,
        },
      },
    ]);
  });
});

test("a variant is retired", async () => {
  const posts: { url: string; body: unknown }[] = [];
  serve(...familyHandlers(posts));
  await renderSupplier("/catalog/fam-1");

  await userEvent.click(await screen.findByRole("button", { name: "Retire" }));

  await waitFor(() => {
    expect(posts.map((post) => post.url)).toEqual([
      "/api/v1/supplier/catalog/variants/var-10/retire",
    ]);
  });
});

test("a retired variant is marked and can be reactivated", async () => {
  const retired = {
    ...family,
    variants: family.variants.map((variant) => ({ ...variant, is_active: false })),
  };
  serve(...familyHandlers([], retired));
  await renderSupplier("/catalog/fam-1");

  expect(await screen.findByRole("button", { name: "Reactivate" })).toBeInTheDocument();
  expect(screen.getByText("retired")).toBeInTheDocument();
});

test("a family whose text is being read says so", async () => {
  serve(...familyHandlers([], { ...family, reading: true }));
  await renderSupplier("/catalog/fam-1");

  expect(await screen.findByText("being read")).toBeInTheDocument();
});

test("the operator gets none of the supplier's catalog buttons", async () => {
  serve(http.get(`${HUB}/api/v1/admin/catalog/families/fam-1`, () => HttpResponse.json(family)));
  await renderOperator("/catalog/fam-1");

  expect(await screen.findByText("For the whole family")).toBeInTheDocument();
  for (const name of ["Add variant", "Retire", "Edit family"]) {
    expect(screen.queryByRole("button", { name })).toBeNull();
  }
});
