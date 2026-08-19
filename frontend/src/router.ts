import {
  createRootRoute,
  createRoute,
  createRouter,
  type RouterHistory,
} from "@tanstack/react-router";

import App from "./App";
import ExpensesPage from "./pages/ExpensesPage";

const rootRoute = createRootRoute({ component: App });

const expensesRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/",
  component: ExpensesPage,
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
