import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { BASE_CURRENCY } from "@/api/currencies";
import { CATEGORY_GROUPING, TOTALS_URL, type TotalsQuery } from "@/api/totals";
import { PeriodTotals } from "@/components/PeriodTotals";

import { MOCK_CATEGORY_TOTALS, MOCK_TOTALS } from "./msw/handlers";
import { server } from "./msw/server";

// Literal dates rather than the current year, so this file names what it asks for and
// does not depend on the day the suite runs.
const QUERY: TotalsQuery = {
  currency: BASE_CURRENCY,
  from_date: "2026-01-01",
  to_date: "2026-12-31",
};

const GROUPED: TotalsQuery = { ...QUERY, group_by: CATEGORY_GROUPING };

function renderPeriodTotals(query: TotalsQuery = QUERY) {
  // A fresh client per test, so nothing is served out of a cache another test filled,
  // and retry off, so the failure cases settle immediately instead of waiting out a
  // backoff. Mounted without the router, so no other request fires: the view takes the
  // parameters as a prop and never reads the URL itself.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <PeriodTotals query={query} />
    </QueryClientProvider>,
  );
}

// Every row as the list of its cells, headers included. The period heading, the category
// lines and the subtotal are different shapes of row, so the whole grid is what the
// assertions below name rather than a count.
function rowTexts() {
  return screen
    .getAllByRole<HTMLTableRowElement>("row")
    .map((row) => [...row.cells].map((cell) => cell.textContent));
}

test("renders a section per period, newest first, each carrying its span", async () => {
  renderPeriodTotals();
  await screen.findByRole("table", { name: "Totals" });
  expect(rowTexts()).toEqual([
    ["2001-03", "2001-03-01 to 2001-03-31"],
    ["Total", "30.00", "EUR"],
    ["2001-02", "2001-02-01 to 2001-02-28"],
    ["None recorded"],
    ["2001-01", "2001-01-01 to 2001-01-31"],
    ["Total", "11.00", "EUR"],
  ]);
});

test("adds a line per category when the grouping was asked for", async () => {
  renderPeriodTotals(GROUPED);
  await screen.findByRole("table", { name: "Totals" });
  // The categories arrive in the order the backend sorted them and are not reordered
  // here, and each period still ends with the subtotal.
  expect(rowTexts()).toEqual([
    ["2001-03", "2001-03-01 to 2001-03-31"],
    ["Stub category", "12.50", "EUR"],
    ["Other stub category", "17.50", "EUR"],
    ["Total", "30.00", "EUR"],
    ["2001-02", "2001-02-01 to 2001-02-28"],
    ["None recorded"],
    ["2001-01", "2001-01-01 to 2001-01-31"],
    ["Stub category", "11.00", "EUR"],
    ["Total", "11.00", "EUR"],
  ]);
});

test("takes the subtotal from the ungrouped request rather than adding the lines up", async () => {
  // A total the category rows do not add up to, which no arithmetic here could produce.
  // Summing amounts this side of the wire is the thing sending them as strings exists to
  // avoid, and this is what proves it is not happening.
  server.use(
    http.get(TOTALS_URL, ({ request }) =>
      HttpResponse.json(
        new URL(request.url).searchParams.get("group_by") === null
          ? [{ ...MOCK_TOTALS[0], amount: "999.99" }]
          : MOCK_CATEGORY_TOTALS.slice(0, 2),
      ),
    ),
  );
  renderPeriodTotals(GROUPED);
  await screen.findByRole("table", { name: "Totals" });
  expect(rowTexts()).toEqual([
    ["2001-03", "2001-03-01 to 2001-03-31"],
    ["Stub category", "12.50", "EUR"],
    ["Other stub category", "17.50", "EUR"],
    ["Total", "999.99", "EUR"],
  ]);
});

test("says a period holds nothing rather than showing it as zero", async () => {
  // The backend leaves amount off a period nobody spent in, which is a different fact
  // from a month of refunds that netted to 0.00. Rendering one as the other would throw
  // that distinction away.
  server.use(
    http.get(TOTALS_URL, () =>
      HttpResponse.json([
        { period: "2001-02", from_date: "2001-02-01", to_date: "2001-02-28" },
      ]),
    ),
  );
  renderPeriodTotals();
  await screen.findByRole("table", { name: "Totals" });
  expect(rowTexts()).toEqual([
    ["2001-02", "2001-02-01 to 2001-02-28"],
    ["None recorded"],
  ]);
});

test("shows a status while the request is in flight", () => {
  renderPeriodTotals();
  expect(screen.getByRole("status").textContent).toBe("Loading totals...");
});

test("shows an alert when the endpoint fails", async () => {
  server.use(
    http.get(TOTALS_URL, () =>
      HttpResponse.json({ detail: "expenses unavailable" }, { status: 503 }),
    ),
  );
  renderPeriodTotals();
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the totals.");
});

test("shows an alert when only the grouped request fails", async () => {
  // The two requests are one view: a breakdown that did not arrive cannot be shown as a
  // period with no categories, which is what a month holding nothing looks like.
  server.use(
    http.get(TOTALS_URL, ({ request }) =>
      new URL(request.url).searchParams.get("group_by") === null
        ? HttpResponse.json(MOCK_TOTALS)
        : HttpResponse.json({ detail: "expenses unavailable" }, { status: 503 }),
    ),
  );
  renderPeriodTotals(GROUPED);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the totals.");
});

test("shows an alert when the payload is not a list", async () => {
  // Nothing generates a client from a schema here, so the guard in src/api/totals.ts is
  // the only thing between a drifted backend and a render that reads undefined.
  server.use(http.get(TOTALS_URL, () => HttpResponse.json({ totals: [] })));
  renderPeriodTotals();
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the totals.");
});

test("shows an alert when an amount arrives as a number", async () => {
  // The backend pins amount to str(Decimal) on its side; this is the frontend half of
  // that contract, and a JSON number is how it would break.
  server.use(
    http.get(TOTALS_URL, () =>
      HttpResponse.json([{ ...MOCK_TOTALS[0], amount: 30.0 }]),
    ),
  );
  renderPeriodTotals();
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the totals.");
});

test("shows an alert when an absent amount arrives as null", async () => {
  // exclude_none is what makes the key absent rather than null, and "absent" is what the
  // None-recorded branch reads. A null would render as a period holding an empty amount.
  server.use(
    http.get(TOTALS_URL, () =>
      HttpResponse.json([
        {
          period: "2001-02",
          from_date: "2001-02-01",
          to_date: "2001-02-28",
          amount: null,
          currency: null,
        },
      ]),
    ),
  );
  renderPeriodTotals();
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the totals.");
});

test("shows a range that matches nothing as a row rather than an alert", async () => {
  // A valid range holding no expenses is a 200 with [], for the reason an empty table
  // is: it is an answer and not a fault.
  server.use(http.get(TOTALS_URL, () => HttpResponse.json([])));
  renderPeriodTotals();
  await screen.findByRole("table", { name: "Totals" });
  expect(screen.getByRole("cell").textContent).toBe("No expenses in this range.");
});

test("asks the API for the parameters it was given", async () => {
  // The conversion, the filtering and the summing are all the backend's, so the whole of
  // this view's half of the feature is that these leave the browser. period is always
  // sent because the backend refuses an absent one, and group_by only when grouping.
  const requested: Record<string, string | null>[] = [];
  server.use(
    http.get(TOTALS_URL, ({ request }) => {
      const params = new URL(request.url).searchParams;
      requested.push({
        period: params.get("period"),
        group_by: params.get("group_by"),
        currency: params.get("currency"),
        from_date: params.get("from_date"),
        to_date: params.get("to_date"),
      });
      return HttpResponse.json(MOCK_TOTALS);
    }),
  );
  renderPeriodTotals({
    currency: "EUR",
    from_date: "2025-01-01",
    to_date: "2025-12-31",
  });
  await screen.findByRole("table", { name: "Totals" });
  expect(requested).toEqual([
    {
      period: "month",
      group_by: null,
      currency: "EUR",
      from_date: "2025-01-01",
      to_date: "2025-12-31",
    },
  ]);
});

test("makes the second request only when the grouping is asked for", async () => {
  const requested: (string | null)[] = [];
  server.use(
    http.get(TOTALS_URL, ({ request }) => {
      const params = new URL(request.url).searchParams;
      requested.push(params.get("group_by"));
      return HttpResponse.json(
        params.get("group_by") === null ? MOCK_TOTALS : MOCK_CATEGORY_TOTALS,
      );
    }),
  );
  renderPeriodTotals(GROUPED);
  await screen.findByRole("table", { name: "Totals" });
  // Both, in either order: they are two independent requests and neither waits on the
  // other, so membership is what this can assert and not a sequence.
  expect(requested).toHaveLength(2);
  expect(requested).toContain(null);
  expect(requested).toContain(CATEGORY_GROUPING);
});
