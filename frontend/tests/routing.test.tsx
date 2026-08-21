import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { createAppRouter } from "@/router";

function renderAppAt(path: string) {
  // A memory history rather than the browser's, so each test starts on the route it
  // names and nothing leaks into the next one through the jsdom URL. The client is the
  // router's context as well as the provider's value, which is what the loaders read.
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
}

test("serves the expenses table at the root path", async () => {
  renderAppAt("/");
  // Awaited, not queried synchronously: the router resolves its first match before it
  // renders anything at all, so nothing exists on the first tick.
  const table = await screen.findByRole("table", { name: "Expenses" });
  expect(table.tagName).toBe("TABLE");
});

// The root route's notFoundComponent, rendered into the shell's Outlet. No twin for its
// errorComponent: reaching that needs a route that throws, and adding one to src/routes/
// to be tested would put a route in the app that the app does not have.
test("answers a path no route matches with the not-found alert", async () => {
  renderAppAt("/nope");
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("No such page.");
  expect(screen.queryByRole("table")).toBeNull();
});

test("keeps the shell around a path no route matches", async () => {
  renderAppAt("/nope");
  await screen.findByRole("alert");
  expect(screen.getByText("Expense Tracker")).toBeTruthy();
});
