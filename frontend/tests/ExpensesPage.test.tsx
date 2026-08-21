import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CURRENCIES_URL } from "@/api/currencies";
import { EXPENSES_URL } from "@/api/expenses";
import { createAppRouter } from "@/router";

import { MOCK_EXPENSES } from "./msw/handlers";
import { server } from "./msw/server";

// The date defaults read the clock, and several assertions below name the month they
// produce. Only Date is faked: react-query, waitFor and user-event all need real timers,
// and freezing those is what hangs the suite.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 7, 20, 12, 0));
});

afterEach(() => {
  vi.useRealTimers();
});

// The whole search the page defaults to under the clock pinned above.
const AUGUST = { currency: "DKK", from_date: "2026-08-01", to_date: "2026-08-31" };

// Mounted through the router rather than bare: the page reads its currency and its dates
// from the URL, so the route is part of what is under test here.
function renderPageAt(path: string) {
  // The client is the router's context as well as the provider's value: the route's
  // loader prefetches through the first, ExpensesTable subscribes through the second,
  // and one request is what proves they are the same cache entry.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createAppRouter(
    queryClient,
    createMemoryHistory({ initialEntries: [path] }),
  );
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

// Records the three parameters of every expenses request and answers each one normally.
function recordRequestedParams() {
  const requested: Record<string, string | null>[] = [];
  server.use(
    http.get(EXPENSES_URL, ({ request }) => {
      const params = new URL(request.url).searchParams;
      requested.push({
        currency: params.get("currency"),
        from_date: params.get("from_date"),
        to_date: params.get("to_date"),
      });
      return HttpResponse.json(MOCK_EXPENSES);
    }),
  );
  return requested;
}

function dateRangeTrigger() {
  return screen.getByRole("button", { name: /^Dates / });
}

function requestedCurrencies(requested: Record<string, string | null>[]) {
  return requested.map((params) => params.currency);
}

function currencySelect() {
  return screen.getByRole<HTMLSelectElement>("combobox", { name: "Currency" });
}

function offeredCurrencies() {
  return screen.getAllByRole<HTMLOptionElement>("option").map((option) => option.value);
}

test("offers the codes the rate table can reach from the base currency", async () => {
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  await waitFor(() => {
    expect(currencySelect().disabled).toBe(false);
  });
  // DKK first as the base, then the two distinct targets stated in that direction. The
  // fixture's SEK -> DKK row is not inverted and its duplicate DKK -> USD is one option.
  expect(offeredCurrencies()).toEqual(["DKK", "EUR", "USD"]);
});

test("requests the currency the URL names", async () => {
  const requested = recordRequestedParams();
  renderPageAt("/?currency=EUR");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requestedCurrencies(requested)).toEqual(["EUR"]);
  expect(currencySelect().value).toBe("EUR");
});

test("defaults to the base currency when the URL names none", async () => {
  const requested = recordRequestedParams();
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requestedCurrencies(requested)).toEqual(["DKK"]);
  expect(currencySelect().value).toBe("DKK");
});

test("defaults to the current month when the URL names no range", async () => {
  const requested = recordRequestedParams();
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requested).toEqual([AUGUST]);
  expect(dateRangeTrigger().textContent).toBe("2026-08-01 to 2026-08-31");
});

test("writes the defaults it filled in back to the URL", async () => {
  // The router commits the validated search to the address bar itself, replacing rather
  // than pushing, so a bare "/" does not stay bare and does not become a back-stop.
  // Pinned because the defaults read the clock: a link copied from a "/" that stayed
  // bare would name whatever month the recipient opened it in.
  const requested = recordRequestedParams();
  const router = renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  await waitFor(() => {
    expect(router.state.location.searchStr).toBe(
      "?currency=DKK&from_date=2026-08-01&to_date=2026-08-31",
    );
  });
  expect(router.state.location.search).toEqual(AUGUST);
  expect(requested).toEqual([AUGUST]);
});

test("ends the default range on the day the month actually ends", async () => {
  // February, so a currentMonth that always reached the 31st would fail here.
  vi.setSystemTime(new Date(2026, 1, 14, 12, 0));
  const requested = recordRequestedParams();
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requested).toEqual([
    { currency: "DKK", from_date: "2026-02-01", to_date: "2026-02-28" },
  ]);
});

test("requests the range the URL names", async () => {
  const requested = recordRequestedParams();
  renderPageAt("/?from_date=2025-01-01&to_date=2025-12-31");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requested).toEqual([
    { currency: "DKK", from_date: "2025-01-01", to_date: "2025-12-31" },
  ]);
  expect(dateRangeTrigger().textContent).toBe("2025-01-01 to 2025-12-31");
});

test("picking a currency keeps the range and asks again", async () => {
  // validateSearch re-defaults an absent parameter, so a navigate that dropped the dates
  // would silently reset them to the current month rather than leaving them alone.
  const requested = recordRequestedParams();
  const router = renderPageAt("/?from_date=2025-01-01&to_date=2025-12-31");
  await screen.findByRole("table", { name: "Expenses" });
  await waitFor(() => {
    expect(currencySelect().disabled).toBe(false);
  });

  await userEvent.selectOptions(currencySelect(), "USD");

  await waitFor(() => {
    expect(router.state.location.search).toEqual({
      currency: "USD",
      from_date: "2025-01-01",
      to_date: "2025-12-31",
    });
  });
  await waitFor(() => {
    expect(requested).toEqual([
      { currency: "DKK", from_date: "2025-01-01", to_date: "2025-12-31" },
      { currency: "USD", from_date: "2025-01-01", to_date: "2025-12-31" },
    ]);
  });
});

test("picking a range keeps the currency, puts it in the URL and asks again", async () => {
  const requested = recordRequestedParams();
  const router = renderPageAt("/?currency=EUR");
  await screen.findByRole("table", { name: "Expenses" });

  await userEvent.click(dateRangeTrigger());
  await userEvent.click(screen.getByRole("button", { name: /August 3rd, 2026/ }));
  await userEvent.click(screen.getByRole("button", { name: /August 10th, 2026/ }));

  await waitFor(() => {
    expect(router.state.location.search).toEqual({
      currency: "EUR",
      from_date: "2026-08-03",
      to_date: "2026-08-10",
    });
  });
  await waitFor(() => {
    expect(requested).toEqual([
      { currency: "EUR", from_date: "2026-08-01", to_date: "2026-08-31" },
      { currency: "EUR", from_date: "2026-08-03", to_date: "2026-08-10" },
    ]);
  });
});

test("passes a date the URL invents through to the backend", async () => {
  // The same rule as the currency below: validateSearch fills in an absent parameter and
  // checks nothing else, so date_range.py is the only place the form is decided.
  const requested: (string | null)[] = [];
  server.use(
    http.get(EXPENSES_URL, ({ request }) => {
      requested.push(new URL(request.url).searchParams.get("from_date"));
      return HttpResponse.json(
        { detail: "from_date must be a date in YYYY-MM-DD form" },
        { status: 422 },
      );
    }),
  );
  renderPageAt("/?from_date=yesterday");
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the expenses.");
  expect(requested).toEqual(["yesterday"]);
  // The control still agrees with the request that failed, rather than showing a date it
  // guessed at.
  expect(dateRangeTrigger().textContent).toBe("yesterday to 2026-08-31");
});

test("passes a range that runs backwards through to the backend", async () => {
  // Only the picker makes an inverted range unreachable, and only through the UI. Typed
  // into the address bar it is the backend's refusal, not a correction here.
  server.use(
    http.get(EXPENSES_URL, () =>
      HttpResponse.json(
        { detail: "from_date must not be after to_date" },
        { status: 422 },
      ),
    ),
  );
  renderPageAt("/?from_date=2026-09-01&to_date=2026-08-01");
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the expenses.");
  expect(dateRangeTrigger().textContent).toBe("2026-09-01 to 2026-08-01");
});

test("passes an empty bound through as the malformed date it is", async () => {
  // An empty ?from_date= is not a request for everything - the backend refuses it the
  // way it refuses an empty ?currency=.
  const requested: (string | null)[] = [];
  server.use(
    http.get(EXPENSES_URL, ({ request }) => {
      requested.push(new URL(request.url).searchParams.get("from_date"));
      return HttpResponse.json(
        { detail: "from_date must be a date in YYYY-MM-DD form" },
        { status: 422 },
      );
    }),
  );
  renderPageAt("/?from_date=");
  await screen.findByRole("alert");
  expect(requested).toEqual([""]);
});

test("passes a code the URL invents through to the backend", async () => {
  // validateSearch fills in an absent parameter and checks nothing else, so the 422 the
  // backend answers with is what the page reports - as its ordinary failure, since the
  // frontend reads no detail out of the body.
  const requested: (string | null)[] = [];
  server.use(
    http.get(EXPENSES_URL, ({ request }) => {
      requested.push(new URL(request.url).searchParams.get("currency"));
      return HttpResponse.json(
        { detail: "currency must be an ISO 4217 code" },
        { status: 422 },
      );
    }),
  );
  renderPageAt("/?currency=euro");
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the expenses.");
  expect(requested).toEqual(["euro"]);
  // The control still agrees with the request that failed, rather than showing DKK.
  expect(currencySelect().value).toBe("euro");
});

test("an unavailable rate table leaves the base currency and the expenses alone", async () => {
  server.use(
    http.get(CURRENCIES_URL, () =>
      HttpResponse.json({ detail: "currencies unavailable" }, { status: 503 }),
    ),
  );
  renderPageAt("/");
  // The expenses are a separate request and are not held hostage by the rate table.
  await screen.findByRole("table", { name: "Expenses" });
  expect(screen.getAllByRole("row")).toHaveLength(MOCK_EXPENSES.length + 1);
  await waitFor(() => {
    expect(currencySelect().disabled).toBe(true);
  });
  expect(offeredCurrencies()).toEqual(["DKK"]);
});

test("an empty rate table is not an error, and leaves the base currency", async () => {
  // 200 with [] is a rate table nobody has run the loader against yet, which the backend
  // reports as a working server for the reason an empty ledger is one.
  server.use(http.get(CURRENCIES_URL, () => HttpResponse.json([])));
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  await waitFor(() => {
    expect(currencySelect().disabled).toBe(false);
  });
  expect(offeredCurrencies()).toEqual(["DKK"]);
});

test("a rate payload of the wrong shape is refused, not read", async () => {
  // The guard in src/api/currencies.ts is the only thing between a drifted backend and a
  // filter built out of undefined, exactly as its twin in src/api/expenses.ts is for the
  // table. A numeric rate is how it would break.
  server.use(
    http.get(CURRENCIES_URL, () =>
      HttpResponse.json([
        { from_currency: "DKK", to_currency: "EUR", exchange_rate: 7.65 },
      ]),
    ),
  );
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  await waitFor(() => {
    expect(currencySelect().disabled).toBe(true);
  });
  expect(offeredCurrencies()).toEqual(["DKK"]);
});
