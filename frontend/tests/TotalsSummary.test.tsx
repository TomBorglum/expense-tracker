import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { CREDIT_CLASS } from "@/amounts";
import { BASE_CURRENCY } from "@/api/currencies";
import { CATEGORY_GROUPING, TOTALS_URL, type TotalsQuery } from "@/api/totals";
import { PeriodTotals } from "@/components/PeriodTotals";
import { TotalsSummary } from "@/components/TotalsSummary";

import { MOCK_TOTALS, totalsCollection } from "./msw/handlers";
import { server } from "./msw/server";

// Literal dates rather than the current year, so this file names what it asks for and
// does not depend on the day the suite runs.
const QUERY: TotalsQuery = {
  currency: BASE_CURRENCY,
  from_date: "2026-01-01",
  to_date: "2026-12-31",
};

const GROUPED: TotalsQuery = { ...QUERY, group_by: CATEGORY_GROUPING };

function client() {
  // Retry off, so the failure case settles immediately instead of waiting out a backoff.
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderSummary(query: TotalsQuery = QUERY) {
  render(
    <QueryClientProvider client={client()}>
      <TotalsSummary query={query} />
    </QueryClientProvider>,
  );
}

test("shows the range average with its currency", async () => {
  renderSummary();
  // 13.67 is the backend's own arithmetic over the mocked amounts, so finding it proves
  // the figure travelled over the request rather than being computed here.
  expect((await screen.findByRole("definition")).textContent).toBe("13.67 EUR");
});

test("names the figure as the term its value defines", async () => {
  // A description list, not two unrelated divs: the label and the value are a pair, so a
  // reader is told which figure the number is. These roles are what dt and dd map to.
  renderSummary();
  expect((await screen.findByRole("term")).textContent).toBe("Average per month");
  expect(screen.getByRole("definition").textContent).toBe("13.67 EUR");
});

test("shows the same figure whether or not the grouping is on", async () => {
  // The summary is a figure about the range, which grouping re-keys the rows of without
  // changing, so the toggle above must not move it.
  renderSummary(GROUPED);
  expect((await screen.findByRole("definition")).textContent).toBe("13.67 EUR");
});

test("says a range holding nothing records none rather than averaging zero", async () => {
  // No extent is no calendar to divide by. "None recorded" for the same reason a period
  // with no amount says it: absent is not 0.00, which a range of credits could net to.
  server.use(http.get(TOTALS_URL, () => totalsCollection([], [])));
  renderSummary();
  expect((await screen.findByRole("definition")).textContent).toBe("None recorded");
});

test("shows a range that nets negative as a credit", async () => {
  server.use(
    http.get(TOTALS_URL, () =>
      totalsCollection(MOCK_TOTALS, [{ currency: "EUR", average: "-1.25" }]),
    ),
  );
  renderSummary();
  const shown = await screen.findByRole("definition");
  // Rewritten by src/amounts.ts alone, as every other amount on the page is.
  expect(shown.textContent).toBe("+1.25 EUR");
  expect(shown.className).toContain(CREDIT_CLASS);
});

test("renders nothing when the request fails, leaving the table its one alert", async () => {
  // One failed request, one alert. The table below owns it, so this side stays silent
  // rather than announcing the same failure to a screen reader twice.
  server.use(
    http.get(TOTALS_URL, () =>
      HttpResponse.json({ detail: "expenses unavailable" }, { status: 503 }),
    ),
  );
  render(
    <QueryClientProvider client={client()}>
      <TotalsSummary query={QUERY} />
      <PeriodTotals query={QUERY} />
    </QueryClientProvider>,
  );
  expect(await screen.findAllByRole("alert")).toHaveLength(1);
  expect(screen.queryByRole("definition")).toBeNull();
});

test("shows an alert when an average arrives as a number", async () => {
  // The guard's job: a numeric average is a contract violation, not a value to coerce,
  // so the whole request is refused and the table below reports it.
  server.use(
    http.get(TOTALS_URL, () =>
      totalsCollection(MOCK_TOTALS, [{ currency: "EUR", average: 13.67 }]),
    ),
  );
  render(
    <QueryClientProvider client={client()}>
      <TotalsSummary query={QUERY} />
      <PeriodTotals query={QUERY} />
    </QueryClientProvider>,
  );
  await screen.findByRole("alert");
  expect(screen.queryByRole("definition")).toBeNull();
});

test("refuses a summary whose currency key is absent", async () => {
  // The asymmetry with a row's optional keys is the contract: an entry exists only for a
  // currency that has expenses, so a missing key is a refusal and not an empty figure.
  server.use(
    http.get(TOTALS_URL, () => totalsCollection(MOCK_TOTALS, [{ average: "13.67" }])),
  );
  render(
    <QueryClientProvider client={client()}>
      <TotalsSummary query={QUERY} />
      <PeriodTotals query={QUERY} />
    </QueryClientProvider>,
  );
  await screen.findByRole("alert");
  expect(screen.queryByRole("definition")).toBeNull();
});

test("costs one request when it renders beside the table", async () => {
  // Both read the ungrouped key, so react-query serves them from one cache entry and
  // deduplicates the fetch they start together. A conditional render that split them
  // would double the request, which is what this notices.
  const requested: string[] = [];
  server.use(
    http.get(TOTALS_URL, ({ request }) => {
      requested.push(new URL(request.url).search);
      return totalsCollection(MOCK_TOTALS);
    }),
  );
  render(
    <QueryClientProvider client={client()}>
      <TotalsSummary query={QUERY} />
      <PeriodTotals query={QUERY} />
    </QueryClientProvider>,
  );
  await screen.findByRole("definition");
  await screen.findByRole("table", { name: "Totals" });
  expect(requested).toHaveLength(1);
});
