import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CATEGORY_GROUPING, TOTALS_URL } from "@/api/totals";
import { createAppRouter } from "@/router";

import { MOCK_CATEGORY_TOTALS, MOCK_TOTALS } from "./msw/handlers";
import { server } from "./msw/server";

// The date defaults read the clock, and several assertions below name the year they
// produce. Only Date is faked: react-query, waitFor and user-event all need real timers,
// and freezing those is what hangs the suite.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 7, 20, 12, 0));
});

afterEach(() => {
  vi.useRealTimers();
});

// The whole ungrouped request the page defaults to under the clock pinned above.
const YEAR = {
  period: "month",
  group_by: null,
  currency: "DKK",
  from_date: "2026-01-01",
  to_date: "2026-12-31",
};

// Mounted through the router rather than bare: the page reads its currency, its dates and
// its grouping from the URL, so the route is part of what is under test here.
function renderPageAt(path: string) {
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

// Records the five parameters of every totals request and answers each one normally.
function recordRequestedParams() {
  const requested: Record<string, string | null>[] = [];
  server.use(
    http.get(TOTALS_URL, ({ request }) => {
      const params = new URL(request.url).searchParams;
      const grouping = params.get("group_by");
      requested.push({
        period: params.get("period"),
        group_by: grouping,
        currency: params.get("currency"),
        from_date: params.get("from_date"),
        to_date: params.get("to_date"),
      });
      return HttpResponse.json(grouping === null ? MOCK_TOTALS : MOCK_CATEGORY_TOTALS);
    }),
  );
  return requested;
}

function dateRangeTrigger() {
  return screen.getByRole("button", { name: /^Dates / });
}

function currencySelect() {
  return screen.getByRole<HTMLSelectElement>("combobox", { name: "Currency" });
}

function categoryToggle() {
  return screen.getByRole<HTMLInputElement>("checkbox", { name: "By category" });
}

function ungrouped(requested: Record<string, string | null>[]) {
  return requested.filter((params) => params.group_by === null);
}

function grouped(requested: Record<string, string | null>[]) {
  return requested.filter((params) => params.group_by === CATEGORY_GROUPING);
}

test("defaults to the whole current year when the URL names no range", async () => {
  const requested = recordRequestedParams();
  renderPageAt("/totals");
  await screen.findByRole("table", { name: "Totals" });
  expect(requested).toEqual([YEAR]);
  expect(dateRangeTrigger().textContent).toBe("2026-01-01 to 2026-12-31");
});

test("defaults to the base currency when the URL names none", async () => {
  const requested = recordRequestedParams();
  renderPageAt("/totals");
  await screen.findByRole("table", { name: "Totals" });
  expect(ungrouped(requested).map((params) => params.currency)).toEqual(["DKK"]);
  expect(currencySelect().value).toBe("DKK");
});

test("requests the currency and the range the URL names", async () => {
  const requested = recordRequestedParams();
  renderPageAt("/totals?currency=EUR&from_date=2025-03-15&to_date=2025-05-10");
  await screen.findByRole("table", { name: "Totals" });
  expect(requested).toEqual([
    {
      period: "month",
      group_by: null,
      currency: "EUR",
      from_date: "2025-03-15",
      to_date: "2025-05-10",
    },
  ]);
});

test("is ungrouped until the URL asks for the grouping", async () => {
  const requested = recordRequestedParams();
  renderPageAt("/totals");
  await screen.findByRole("table", { name: "Totals" });
  // One request, not two: absent group_by means ungrouped on both sides of the wire, so
  // the off state costs no second round trip.
  expect(requested).toEqual([YEAR]);
  expect(categoryToggle().checked).toBe(false);
});

test("asks for both payloads when the URL asks for the grouping", async () => {
  const requested = recordRequestedParams();
  renderPageAt("/totals?group_by=category");
  await screen.findByRole("table", { name: "Totals" });
  await waitFor(() => {
    expect(requested).toHaveLength(2);
  });
  // One of each, in either order: they are two independent requests and neither waits
  // on the other.
  expect(ungrouped(requested)).toHaveLength(1);
  expect(grouped(requested)).toHaveLength(1);
  expect(categoryToggle().checked).toBe(true);
});

test("ignores a group_by the backend would refuse", async () => {
  // validateSearch fills in an absent parameter and validates nothing else, but this one
  // has no value to fall back to: anything that is not the grouping is the absence of it,
  // so a typo asks for the ungrouped view rather than sending a 422 on its way.
  const requested = recordRequestedParams();
  renderPageAt("/totals?group_by=currency");
  await screen.findByRole("table", { name: "Totals" });
  expect(requested).toEqual([YEAR]);
  expect(categoryToggle().checked).toBe(false);
});

test("turning the grouping on keeps the currency and the range", async () => {
  const user = userEvent.setup();
  const requested = recordRequestedParams();
  const router = renderPageAt("/totals?currency=EUR");
  await screen.findByRole("table", { name: "Totals" });
  await user.click(categoryToggle());
  await waitFor(() => {
    expect(grouped(requested)).toHaveLength(1);
  });
  // Two requests in total, not three: the ungrouped one is keyed on a range that did not
  // change, so the subtotal comes back out of the cache and turning the grouping on
  // costs exactly the payload it adds.
  expect(requested).toHaveLength(2);
  // Every navigate spreads the whole search, because validateSearch re-defaults an
  // absent parameter: omitting from_date here would silently reset the range.
  expect(router.state.location.search).toEqual({
    currency: "EUR",
    from_date: "2026-01-01",
    to_date: "2026-12-31",
    group_by: CATEGORY_GROUPING,
  });
  expect(grouped(requested).at(-1)?.currency).toBe("EUR");
});

test("turning the grouping off drops the parameter from the URL", async () => {
  const user = userEvent.setup();
  recordRequestedParams();
  const router = renderPageAt("/totals?group_by=category");
  await screen.findByRole("table", { name: "Totals" });
  // Asserted before the click as well, so a view that never had the lines cannot pass
  // the one after it. A disabled query keeps serving its cache, so the breakdown is
  // still there to be read wrongly once the toggle goes off. Two of them: the fixture
  // spends on that category in two of its three periods.
  expect(screen.getAllByRole("rowheader", { name: "Stub category" })).toHaveLength(2);
  await user.click(categoryToggle());
  await waitFor(() => {
    expect(categoryToggle().checked).toBe(false);
  });
  expect(screen.queryAllByRole("rowheader", { name: "Stub category" })).toHaveLength(0);
  // Undefined rather than an off-value: absent is what ungrouped means on the wire, so
  // it is what it means here too.
  expect(router.state.location.search).toEqual({
    currency: "DKK",
    from_date: "2026-01-01",
    to_date: "2026-12-31",
  });
});

test("picking a currency keeps the range and the grouping, and asks again", async () => {
  const user = userEvent.setup();
  const requested = recordRequestedParams();
  const router = renderPageAt("/totals?group_by=category");
  await screen.findByRole("table", { name: "Totals" });
  await waitFor(() => {
    expect(currencySelect().disabled).toBe(false);
  });
  await user.selectOptions(currencySelect(), "EUR");
  await waitFor(() => {
    expect(ungrouped(requested).at(-1)?.currency).toBe("EUR");
  });
  expect(router.state.location.search).toEqual({
    currency: "EUR",
    from_date: "2026-01-01",
    to_date: "2026-12-31",
    group_by: CATEGORY_GROUPING,
  });
});

test("picking a range keeps the currency and the grouping, and asks again", async () => {
  const user = userEvent.setup();
  const requested = recordRequestedParams();
  const router = renderPageAt("/totals?currency=EUR&group_by=category");
  await screen.findByRole("table", { name: "Totals" });

  // The panels open on the months the default range starts and ends in, which under the
  // whole-year default is January on the left and December on the right.
  await user.click(dateRangeTrigger());
  await user.click(screen.getByRole("button", { name: /January 5th, 2026/ }));
  await user.click(screen.getByRole("button", { name: /December 20th, 2026/ }));

  await waitFor(() => {
    expect(router.state.location.search).toEqual({
      currency: "EUR",
      from_date: "2026-01-05",
      to_date: "2026-12-20",
      group_by: CATEGORY_GROUPING,
    });
  });
  await waitFor(() => {
    expect(ungrouped(requested).at(-1)).toEqual({
      period: "month",
      group_by: null,
      currency: "EUR",
      from_date: "2026-01-05",
      to_date: "2026-12-20",
    });
  });
  // Both halves of the view follow the range, not just the one the picker sits above.
  expect(grouped(requested).at(-1)?.from_date).toBe("2026-01-05");
});

test("shows the totals rather than the expenses table", async () => {
  renderPageAt("/totals");
  const table = await screen.findByRole("table", { name: "Totals" });
  expect(table.tagName).toBe("TABLE");
  expect(screen.queryByRole("table", { name: "Expenses" })).toBeNull();
});
