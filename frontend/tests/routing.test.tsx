import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { createAppRouter } from "@/router";

function renderAppAt(path: string) {
  // A memory history rather than the browser's, so each test starts on the route it
  // names and nothing leaks into the next one through the jsdom URL.
  const router = createAppRouter(createMemoryHistory({ initialEntries: [path] }));
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
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

test("serves the period totals at /totals", async () => {
  renderAppAt("/totals");
  const table = await screen.findByRole("table", { name: "Totals" });
  expect(table.tagName).toBe("TABLE");
});

test("names both routes in the navigation", async () => {
  renderAppAt("/");
  // The header is a nav now that there are two routes, and the links are what make the
  // second reachable without typing its path. Awaited for the reason above: the shell
  // renders with the first match and not before it.
  const links = await screen.findAllByRole("link");
  expect(links.map((link) => link.textContent)).toEqual(["Expenses", "Totals"]);
});

test("marks the current route in the navigation, filters and all", async () => {
  // With a search in the URL, which is the case that silently does not mark: activeOptions
  // includes the search by default, and a link carrying none then matches nothing.
  renderAppAt("/totals?currency=EUR&group_by=category");
  const links = await screen.findAllByRole("link");
  expect(links.map((link) => link.className.includes("btn-active"))).toEqual([
    false,
    true,
  ]);
});
