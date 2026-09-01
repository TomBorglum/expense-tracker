import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";

import { createAppRouter } from "@/router";

// Both routes default their range off the clock, and the assertions below name the days
// that produces. Only Date is faked, for the reason the page tests give: react-query,
// waitFor and user-event all need real timers.
beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(new Date(2026, 7, 20, 12, 0));
});

afterEach(() => {
  vi.useRealTimers();
});

// The whole current year, which is what both views fill an absent bound with.
const YEAR = { from_date: "2026-01-01", to_date: "2026-12-31" };

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
  return router;
}

function navLink(name: string) {
  return screen.getByRole("link", { name });
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

test("puts the defaults it filled in into the URL", async () => {
  // A bare path is rewritten, with replace, to the search validateSearch filled in, so
  // every URL names the whole view and a link is worth sending the moment it is copied.
  // The router does this on mount rather than anything here; this is what pins it.
  const router = renderAppAt("/");
  await screen.findByRole("table", { name: "Expenses" });
  expect(router.state.location.search).toEqual({ currency: "DKK", ...YEAR });
});

test("puts the defaults it filled in into the URL on the totals view too", async () => {
  const router = renderAppAt("/totals");
  await screen.findByRole("table", { name: "Totals" });
  expect(router.state.location.search).toEqual({ currency: "DKK", ...YEAR });
});

test("carries the currency and the range from the expenses view to the totals", async () => {
  const user = userEvent.setup();
  const router = renderAppAt("/?currency=EUR&from_date=2025-03-01&to_date=2025-04-30");
  await screen.findByRole("table", { name: "Expenses" });

  await user.click(navLink("Totals"));

  await screen.findByRole("table", { name: "Totals" });
  expect(router.state.location.pathname).toBe("/totals");
  expect(router.state.location.search).toEqual({
    currency: "EUR",
    from_date: "2025-03-01",
    to_date: "2025-04-30",
  });
});

test("carries them back the other way", async () => {
  const user = userEvent.setup();
  const router = renderAppAt(
    "/totals?currency=USD&from_date=2025-06-01&to_date=2025-06-30",
  );
  await screen.findByRole("table", { name: "Totals" });

  await user.click(navLink("Expenses"));

  await screen.findByRole("table", { name: "Expenses" });
  expect(router.state.location.pathname).toBe("/");
  expect(router.state.location.search).toEqual({
    currency: "USD",
    from_date: "2025-06-01",
    to_date: "2025-06-30",
  });
});

test("leaves the grouping behind, the expenses view declaring none", async () => {
  const user = userEvent.setup();
  const router = renderAppAt("/totals?currency=EUR&group_by=category");
  await screen.findByRole("table", { name: "Totals" });

  await user.click(navLink("Expenses"));

  await screen.findByRole("table", { name: "Expenses" });
  expect(router.state.location.search).toEqual({ currency: "EUR", ...YEAR });
});
