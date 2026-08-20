import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { CURRENCIES_URL } from "@/api/currencies";
import { EXPENSES_URL } from "@/api/expenses";
import { createAppRouter } from "@/router";

import { MOCK_EXPENSES } from "./msw/handlers";
import { server } from "./msw/server";

// Mounted through the router rather than bare: the page reads its currency from the URL,
// so the route is part of what is under test here.
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

// Records the currency of every expenses request and answers each one normally.
function recordRequestedCurrencies() {
  const requested: (string | null)[] = [];
  server.use(
    http.get(EXPENSES_URL, ({ request }) => {
      requested.push(new URL(request.url).searchParams.get("currency"));
      return HttpResponse.json(MOCK_EXPENSES);
    }),
  );
  return requested;
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
  const requested = recordRequestedCurrencies();
  renderPageAt("/?currency=EUR");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requested).toEqual(["EUR"]);
  expect(currencySelect().value).toBe("EUR");
});

test("defaults to the base currency when the URL names none", async () => {
  const requested = recordRequestedCurrencies();
  renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requested).toEqual(["DKK"]);
  expect(currencySelect().value).toBe("DKK");
});

test("picking a currency puts it in the URL and asks again", async () => {
  const requested = recordRequestedCurrencies();
  const router = renderPageAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  await waitFor(() => {
    expect(currencySelect().disabled).toBe(false);
  });

  await userEvent.selectOptions(currencySelect(), "USD");

  await waitFor(() => {
    expect(router.state.location.search).toEqual({ currency: "USD" });
  });
  await waitFor(() => {
    expect(requested).toEqual(["DKK", "USD"]);
  });
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
