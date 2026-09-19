import type { HubSchemas } from "@sanovio/api";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

import { HUB, renderSupplier, serve } from "../test/harness";

type Request = HubSchemas["schemas"]["SupplierRequestView"];

const request: Request = {
  assessment_id: "asm-1",
  hospital: "Hospital H-7F3A",
  article_no: "300912",
  variant_label: "BD Plastipak™ Luer-Lok™ 10 ml",
  family: "BD Plastipak™ Luer-Lok™",
  status: "AWAITING_ANSWERS",
  created_at: "2026-09-19T09:00:00Z",
  questions: [
    {
      id: "q-mdr",
      attribute_key: "mdr_class",
      text: "In welche MDR-Risikoklasse ist das Produkt eingestuft?",
      language: "de",
      expected_answer: { type: "enum", options: ["I", "IIA", "IIB"] },
      status: "SENT",
      draft: null,
    },
    {
      id: "q-dehp",
      attribute_key: "dehp_free",
      text: "Ist das Produkt DEHP-frei?",
      language: "de",
      expected_answer: { type: "bool" },
      status: "SENT",
      draft: null,
    },
    {
      id: "q-id",
      attribute_key: "inner_diameter_mm",
      text: "Wie gross ist der Innendurchmesser?",
      language: "de",
      expected_answer: { type: "number", unit: "mm" },
      status: "SENT",
      draft: null,
    },
  ],
};

test("the inbox shows our product and only the hospital's alias", async () => {
  serve(http.get(`${HUB}/api/v1/supplier/requests`, () => HttpResponse.json([request])));
  await renderSupplier("/");

  expect(await screen.findByRole("link", { name: request.variant_label })).toBeInTheDocument();
  expect(screen.getByText("Hospital H-7F3A")).toBeInTheDocument();
  expect(screen.getByText("3 open")).toBeInTheDocument();
});

test("typed values, comments and cannot-provide are saved and submitted", async () => {
  const saved: unknown[] = [];
  let submitted = 0;
  serve(
    http.get(`${HUB}/api/v1/supplier/requests/asm-1`, () => HttpResponse.json(request)),
    http.put(`${HUB}/api/v1/supplier/requests/asm-1/answers`, async ({ request: sent }) => {
      saved.push(await sent.json());
      return HttpResponse.json(request);
    }),
    http.post(`${HUB}/api/v1/supplier/requests/asm-1/submit`, () => {
      submitted += 1;
      return HttpResponse.json({ ...request, status: "ASSESSING" });
    }),
  );
  await renderSupplier("/requests/asm-1");

  await userEvent.selectOptions(
    await screen.findByLabelText(request.questions[0]?.text ?? ""),
    "IIA",
  );
  await userEvent.type(
    screen.getByLabelText(`Comment on: ${request.questions[1]?.text ?? ""}`),
    "Zylinder und Stopfen enthalten kein DEHP.",
  );
  const [familyWide] = screen.getAllByLabelText("Applies to the whole product family");
  if (!familyWide) throw new Error("no family checkbox");
  await userEvent.click(familyWide);
  const cannot = screen.getAllByLabelText("We cannot provide this").at(-1);
  if (!cannot) throw new Error("no cannot-provide checkbox");
  await userEvent.click(cannot);
  await userEvent.click(screen.getByRole("button", { name: "Submit answers" }));

  await waitFor(() => {
    expect(submitted).toBe(1);
  });
  expect(saved).toEqual([
    {
      answers: [
        {
          question_id: "q-mdr",
          value: { type: "enum", value: "IIA" },
          comment: null,
          cannot_provide: false,
          applies_to_family: true,
        },
        {
          question_id: "q-dehp",
          value: null,
          comment: "Zylinder und Stopfen enthalten kein DEHP.",
          cannot_provide: false,
          applies_to_family: false,
        },
        {
          question_id: "q-id",
          value: null,
          comment: null,
          cannot_provide: true,
          applies_to_family: false,
        },
      ],
    },
  ]);
});

test("an incomplete batch is refused with the hub's reason", async () => {
  serve(
    http.get(`${HUB}/api/v1/supplier/requests/asm-1`, () => HttpResponse.json(request)),
    http.put(`${HUB}/api/v1/supplier/requests/asm-1/answers`, () => HttpResponse.json(request)),
    http.post(`${HUB}/api/v1/supplier/requests/asm-1/submit`, () =>
      HttpResponse.json({ detail: "unanswered questions: q-dehp, q-id" }, { status: 422 }),
    ),
  );
  await renderSupplier("/requests/asm-1");

  await userEvent.click(await screen.findByRole("button", { name: "Submit answers" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("unanswered questions: q-dehp, q-id");
});

test("in development the simulator can answer for us", async () => {
  let simulated = 0;
  serve(
    http.get(`${HUB}/api/v1/supplier/requests/asm-1`, () => HttpResponse.json(request)),
    http.post(`${HUB}/api/v1/dev/assessments/asm-1/simulate-supplier`, () => {
      simulated += 1;
      return HttpResponse.json({ status: "ASSESSING" });
    }),
  );
  await renderSupplier("/requests/asm-1");

  await userEvent.click(
    await screen.findByRole("button", { name: "Let the simulator answer (dev)" }),
  );

  await waitFor(() => {
    expect(simulated).toBe(1);
  });
});
