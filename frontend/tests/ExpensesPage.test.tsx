import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { CATEGORIES_URL } from "@/api/categories";
import { CURRENCIES_URL } from "@/api/currencies";
import { EXPENSES_URL } from "@/api/expenses";
import { createAppRouter } from "@/router";

import { MOCK_CATEGORIES, MOCK_EXPENSES } from "./msw/handlers";
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

// The whole search the page defaults to under the clock pinned above. The same year
// /totals defaults to, so switching between the two views changes nothing.
const YEAR = { currency: "DKK", from_date: "2026-01-01", to_date: "2026-12-31" };

// Mounted through the router rather than bare: the page reads its currency and its dates
// from the URL, so the route is part of what is under test here.
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

// Records the category list of every expenses request, as the repeated key the backend
// reads, and answers each one normally.
function recordRequestedCategories() {
  const requested: string[][] = [];
  server.use(
    http.get(EXPENSES_URL, ({ request }) => {
      requested.push(new URL(request.url).searchParams.getAll("category"));
      return HttpResponse.json(MOCK_EXPENSES);
    }),
  );
  return requested;
}

function dateRangeTrigger() {
  return screen.getByRole("button", { name: /^Dates / });
}

function categoryTrigger() {
  return screen.getByRole("button", { name: /^Categories / });
}

async function categoryTriggerEnabled() {
  await waitFor(() => {
    expect(categoryTrigger().hasAttribute("disabled")).toBe(false);
  });
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

test("defaults to the whole current year when the URL names no range", async () => {
  const requested = recordRequestedParams();
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requested).toEqual([YEAR]);
  expect(dateRangeTrigger().textContent).toBe("2026-01-01 to 2026-12-31");
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

  // The panels open on the months the default range starts and ends in, which under the
  // whole-year default is January on the left and December on the right.
  await userEvent.click(dateRangeTrigger());
  await userEvent.click(screen.getByRole("button", { name: /January 5th, 2026/ }));
  await userEvent.click(screen.getByRole("button", { name: /December 20th, 2026/ }));

  await waitFor(() => {
    expect(router.state.location.search).toEqual({
      currency: "EUR",
      from_date: "2026-01-05",
      to_date: "2026-12-20",
    });
  });
  await waitFor(() => {
    expect(requested).toEqual([
      { currency: "EUR", from_date: "2026-01-01", to_date: "2026-12-31" },
      { currency: "EUR", from_date: "2026-01-05", to_date: "2026-12-20" },
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
  expect(dateRangeTrigger().textContent).toBe("yesterday to 2026-12-31");
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

test("offers the categories the backend lists, in its order", async () => {
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  await categoryTriggerEnabled();
  await userEvent.click(categoryTrigger());
  const names = screen
    .getAllByRole("checkbox")
    .map((box) => (box as HTMLInputElement).labels?.[0]?.textContent);
  expect(names).toEqual(MOCK_CATEGORIES.map((item) => item.category));
});

test("sends no category when the URL names none", async () => {
  const requested = recordRequestedCategories();
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requested).toEqual([[]]);
  expect(categoryTrigger().textContent).toBe("All categories");
});

test("requests the categories the URL names, once each", async () => {
  // The repeated key both the app URL and the API spell.
  const requested = recordRequestedCategories();
  renderPageAt("/?category=Stub%20category&category=Other%20stub%20category");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requested).toEqual([["Stub category", "Other stub category"]]);
  expect(categoryTrigger().textContent).toBe("Stub category, Other stub category");
});

test("reads a single category the URL names", async () => {
  // One value arrives as a string rather than a one-element list, and is a filter all
  // the same - which is what a hand-typed URL produces.
  const requested = recordRequestedCategories();
  renderPageAt("/?category=Stub%20category");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requested).toEqual([["Stub category"]]);
  await categoryTriggerEnabled();
  await userEvent.click(categoryTrigger());
  expect(
    screen.getByRole<HTMLInputElement>("checkbox", { name: "Stub category" }).checked,
  ).toBe(true);
});

test("ticking a category keeps the currency and the range, and asks again", async () => {
  const requested = recordRequestedCategories();
  const router = renderPageAt("/?currency=EUR&from_date=2025-01-01&to_date=2025-12-31");
  await screen.findByRole("table", { name: "Expenses" });
  await categoryTriggerEnabled();

  await userEvent.click(categoryTrigger());
  await userEvent.click(screen.getByRole("checkbox", { name: "Stub category" }));

  // The URL as a string rather than as the parsed search: one value parses back to a
  // bare string, and what matters here is that the other three survived the navigate.
  await waitFor(() => {
    expect(router.state.location.searchStr).toBe(
      "?currency=EUR&from_date=2025-01-01&to_date=2025-12-31&category=Stub+category",
    );
  });
  await waitFor(() => {
    expect(requested).toEqual([[], ["Stub category"]]);
  });
});

test("clearing the selection drops the parameter from the URL", async () => {
  const requested = recordRequestedCategories();
  const router = renderPageAt("/?category=Stub%20category");
  await screen.findByRole("table", { name: "Expenses" });
  await categoryTriggerEnabled();

  await userEvent.click(categoryTrigger());
  await userEvent.click(screen.getByRole("button", { name: "Clear selection" }));

  // Undefined rather than an empty list: absent is what unfiltered means on the wire.
  await waitFor(() => {
    expect(router.state.location.search).toEqual(YEAR);
  });
  await waitFor(() => {
    expect(requested).toEqual([["Stub category"], []]);
  });
});

test("passes an empty category through as the malformed value it is", async () => {
  // An empty ?category= is not a request for everything - the backend refuses it the
  // way it refuses an empty ?currency=.
  const requested: string[][] = [];
  server.use(
    http.get(EXPENSES_URL, ({ request }) => {
      requested.push(new URL(request.url).searchParams.getAll("category"));
      return HttpResponse.json(
        { detail: "category must not be blank" },
        { status: 422 },
      );
    }),
  );
  renderPageAt("/?category=");
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the expenses.");
  expect(requested).toEqual([[""]]);
});

test("an unavailable category list leaves the expenses alone", async () => {
  server.use(
    http.get(CATEGORIES_URL, () =>
      HttpResponse.json({ detail: "expenses unavailable" }, { status: 503 }),
    ),
  );
  renderPageAt("/?category=Stub%20category");
  // The expenses are a separate request and are not held hostage by the list.
  await screen.findByRole("table", { name: "Expenses" });
  expect(screen.getAllByRole("row")).toHaveLength(MOCK_EXPENSES.length + 1);
  await waitFor(() => {
    expect(categoryTrigger().hasAttribute("disabled")).toBe(true);
  });
  // Still agreeing with the request in flight rather than reading as unfiltered.
  expect(categoryTrigger().textContent).toBe("Stub category");
});

test("an empty category list leaves nothing to pick", async () => {
  // 200 with [] is a ledger nobody has run the loader against yet: a working server, and
  // a filter with nothing to offer.
  server.use(http.get(CATEGORIES_URL, () => HttpResponse.json([])));
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  await waitFor(() => {
    expect(categoryTrigger().hasAttribute("disabled")).toBe(true);
  });
});

test("a category payload of the wrong shape is refused, not read", async () => {
  server.use(http.get(CATEGORIES_URL, () => HttpResponse.json([{ category: 42 }])));
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  await waitFor(() => {
    expect(categoryTrigger().hasAttribute("disabled")).toBe(true);
  });
});
