import {
  createRootRoute,
  createRoute,
  createRouter,
  type RouterHistory,
} from "@tanstack/react-router";

import { BASE_CURRENCY } from "./api/currencies";
import { type ExpensesQuery } from "./api/expenses";
import App from "./App";
import { currentMonth } from "./dates";
import ExpensesPage from "./pages/ExpensesPage";

const rootRoute = createRootRoute({ component: App });

// The currency the expenses are presented in and the days they are drawn from, carried
// in the URL so a view is shareable and survives a reload. An alias rather than a second
// declaration: the search is handed to expensesQueryOptions as it stands, so the two
// cannot drift.
export type ExpensesSearch = ExpensesQuery;

const expensesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: ExpensesPage,
  // Supplies the default for an absent parameter and nothing else. A malformed code or
  // date is handed on to the backend, which refuses it with a 422; re-checking either
  // here would put the pattern in conversion.py or date_range.py in a second place to
  // drift from. The date defaults read the clock, which is why the page tests pin it.
  validateSearch: (search: Record<string, unknown>): ExpensesSearch => {
    const month = currentMonth();
    return {
      currency: typeof search.currency === "string" ? search.currency : BASE_CURRENCY,
      from_date: typeof search.from_date === "string" ? search.from_date : month.from,
      to_date: typeof search.to_date === "string" ? search.to_date : month.to,
    };
  },
});

const routeTree = rootRoute.addChildren([expensesRoute]);

// A factory rather than a module-level singleton, so the tests build their own router
// over a memory history instead of sharing navigation state between them.
export function createAppRouter(history?: RouterHistory) {
  return createRouter({ routeTree, history });
}

// Without this declaration Link, useNavigate and useSearch have no type safety, and a
// path that matches no route is accepted rather than rejected at build time.
declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
