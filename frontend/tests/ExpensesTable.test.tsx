import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { BASE_CURRENCY } from "@/api/currencies";
import { EXPENSES_URL } from "@/api/expenses";
import { ExpensesTable } from "@/components/ExpensesTable";

import { MOCK_EXPENSES } from "./msw/handlers";
import { server } from "./msw/server";

function renderExpensesTable(currency = BASE_CURRENCY) {
  // A fresh client per test, so nothing is served out of a cache another test filled,
  // and retry off, so the failure cases settle immediately instead of waiting out a
  // backoff. Mounted without the router, so no other request fires: the table takes the
  // currency as a prop and never reads the URL itself.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <ExpensesTable currency={currency} />
    </QueryClientProvider>,
  );
}

test("renders every expense the API serves, in the order it sends them", async () => {
  renderExpensesTable();
  await screen.findByRole("table", { name: "Expenses" });
  // Column order is pinned here too: the cells come back in document order, so a
  // reordered header would have to reorder these to keep passing.
  const cells = screen.getAllByRole("cell");
  expect(cells.map((cell) => cell.textContent)).toEqual(
    MOCK_EXPENSES.flatMap((expense) => [
      expense.amount,
      expense.currency,
      expense.date,
      expense.category,
      expense.details,
    ]),
  );
});

test("renders one row per expense under the header row", async () => {
  renderExpensesTable();
  await screen.findByRole("table", { name: "Expenses" });
  expect(screen.getAllByRole("row")).toHaveLength(MOCK_EXPENSES.length + 1);
});

test("shows a status while the request is in flight", () => {
  renderExpensesTable();
  expect(screen.getByRole("status").textContent).toBe("Loading expenses...");
});

test("shows an alert when the endpoint fails", async () => {
  server.use(
    http.get(EXPENSES_URL, () =>
      HttpResponse.json({ detail: "expenses unavailable" }, { status: 503 }),
    ),
  );
  renderExpensesTable();
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the expenses.");
});

test("shows an alert when the payload is not a list", async () => {
  // Nothing generates a client from a schema here, so the guard in src/api/expenses.ts
  // is the only thing between a drifted backend and a render that reads undefined.
  server.use(http.get(EXPENSES_URL, () => HttpResponse.json({ expenses: [] })));
  renderExpensesTable();
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the expenses.");
});

test("shows an alert when an amount arrives as a number", async () => {
  // The backend pins amount to str(Decimal) on its side; this is the frontend half of
  // that contract, and a JSON number is how it would break.
  server.use(
    http.get(EXPENSES_URL, () =>
      HttpResponse.json([{ ...MOCK_EXPENSES[0], amount: 13.37 }]),
    ),
  );
  renderExpensesTable();
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the expenses.");
});

test("shows an empty ledger as a row rather than an alert", async () => {
  // 200 with [] is a database nobody has run the loader against yet, which the backend
  // deliberately does not report as a fault.
  server.use(http.get(EXPENSES_URL, () => HttpResponse.json([])));
  renderExpensesTable();
  await screen.findByRole("table", { name: "Expenses" });
  expect(screen.getByRole("cell").textContent).toBe("No expenses loaded.");
});

test("asks the API for the currency it was given", async () => {
  // The conversion is the backend's, so the whole of the table's half of the feature is
  // that this parameter leaves the browser.
  const requested: (string | null)[] = [];
  server.use(
    http.get(EXPENSES_URL, ({ request }) => {
      requested.push(new URL(request.url).searchParams.get("currency"));
      return HttpResponse.json(MOCK_EXPENSES);
    }),
  );
  renderExpensesTable("EUR");
  await screen.findByRole("table", { name: "Expenses" });
  expect(requested).toEqual(["EUR"]);
});
