import type { QueryClient } from "@tanstack/react-query";
import { createRouter, type RouterHistory } from "@tanstack/react-router";

import { routeTree } from "./routeTree.gen";

// A factory rather than a module-level singleton, so the tests build their own router
// over a memory history instead of sharing navigation state between them. The client is
// a parameter for the same reason: it reaches the route loaders as router context, and
// each test builds its own.
export function createAppRouter(queryClient: QueryClient, history?: RouterHistory) {
  return createRouter({
    routeTree,
    history,
    context: { queryClient },
    // Live on one route: the currency and date controls each push a history entry, so
    // back and forward across them is a navigation on a table that can be taller than
    // the viewport.
    scrollRestoration: true,
    // Dead configuration while src/ contains no Link, and kept anyway: it is what a nav
    // added beside a second route would need, and 0 is what stops a preloaded loader
    // reading a stale entry back out of react-query.
    defaultPreload: "intent",
    defaultPreloadStaleTime: 0,
  });
}

// Without this declaration Link, useNavigate and useSearch have no type safety, and a
// path that matches no route is accepted rather than rejected at build time. The
// generated tree augments FileRoutesByPath, which is a different interface.
declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
