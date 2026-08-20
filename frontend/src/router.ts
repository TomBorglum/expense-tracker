import {
  createRootRoute,
  createRoute,
  createRouter,
  type RouterHistory,
} from "@tanstack/react-router";

import { BASE_CURRENCY } from "./api/currencies";
import App from "./App";
import ExpensesPage from "./pages/ExpensesPage";

const rootRoute = createRootRoute({ component: App });

// The currency the expenses are presented in, carried in the URL so a view is shareable
// and survives a reload.
export interface ExpensesSearch {
  currency: string;
}

const expensesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: ExpensesPage,
  // Supplies the default for an absent parameter and nothing else. A malformed code is
  // handed on to the backend, which refuses it with a 422; re-checking it here would put
  // the pattern in conversion.py in a second place to drift from.
  validateSearch: (search: Record<string, unknown>): ExpensesSearch => ({
    currency: typeof search.currency === "string" ? search.currency : BASE_CURRENCY,
  }),
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
