import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { render, screen, waitFor } from "@testing-library/react";
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

test("carries the categories between the views as well", async () => {
  const user = userEvent.setup();
  const router = renderAppAt("/?category=stub-category&category=other-stub-category");
  await screen.findByRole("table", { name: "Expenses" });

  await user.click(navLink("Totals"));

  await screen.findByRole("table", { name: "Totals" });
  expect(router.state.location.search).toEqual({
    currency: "DKK",
    ...YEAR,
    category: ["stub-category", "other-stub-category"],
  });

  await user.click(navLink("Expenses"));

  await screen.findByRole("table", { name: "Expenses" });
  expect(router.state.location.search.category).toEqual([
    "stub-category",
    "other-stub-category",
  ]);
});

test("carries both lists and the root default between the views", async () => {
  // The one state that needs all three keys: everything except a root, with a branch of
  // it kept. If any of the three failed to carry, the selection would change on the way
  // across rather than merely be forgotten.
  const user = userEvent.setup();
  const router = renderAppAt(
    "/?not_category=stub-category&category=stub-category:nested-stub" +
      "&category_default=all",
  );
  await screen.findByRole("table", { name: "Expenses" });

  await user.click(navLink("Totals"));

  await screen.findByRole("table", { name: "Totals" });
  expect(router.state.location.search).toEqual({
    currency: "DKK",
    ...YEAR,
    category: "stub-category:nested-stub",
    not_category: "stub-category",
    category_default: "all",
  });
});

test("leaves no category key behind when the default selection is picked again", async () => {
  // The risk retainSearchParams carries: it keeps a key the next navigate does not
  // mention, so all three have to be navigated as undefined rather than left out -
  // otherwise the default selection would be unreachable from any URL naming one.
  const user = userEvent.setup();
  const router = renderAppAt("/totals?not_category=stub-category&category_default=all");
  await screen.findByRole("table", { name: "Totals" });
  const trigger = screen.getByRole("button", { name: /^Categories / });
  await waitFor(() => {
    expect(trigger.hasAttribute("disabled")).toBe(false);
  });

  await user.click(trigger);
  await user.click(screen.getByRole("button", { name: "Select all" }));

  await waitFor(() => {
    expect(router.state.location.search).toEqual({ currency: "DKK", ...YEAR });
  });
  expect(router.state.location.searchStr).not.toContain("category");
});

test("carries a category slug across the views unsplit", async () => {
  const user = userEvent.setup();
  const router = renderAppAt("/?category=stub-category%3Anested-stub");
  await screen.findByRole("table", { name: "Expenses" });

  await user.click(navLink("Totals"));

  await screen.findByRole("table", { name: "Totals" });
  // One value, retained whole: retainSearchParams copies what validateSearch read, and
  // a separator is nothing either of them knows about. Typed as its own escape here,
  // which is the one form a slug can still arrive percent-encoded in.
  expect(router.state.location.search.category).toBe("stub-category:nested-stub");
});

test("spells a list as a key repeated once per value", async () => {
  // The form an HTML form submits and the backend reads, rather than the JSON array the
  // router would write on its own - so a URL can be typed by hand and pasted as it is.
  const router = renderAppAt("/?category=A&category=B");
  await screen.findByRole("table", { name: "Expenses" });
  const searchStr = router.state.location.searchStr;
  expect(searchStr).toContain("category=A&category=B");
  expect(searchStr).not.toContain("%5B");
  expect(new URLSearchParams(searchStr).getAll("category")).toEqual(["A", "B"]);
});

test("spells the deselected list as a repeated key as well", async () => {
  // The same spelling for the second list, which is what lets the backend read the two
  // on the same terms.
  const router = renderAppAt("/?not_category=A&not_category=B");
  await screen.findByRole("table", { name: "Expenses" });
  const searchStr = router.state.location.searchStr;
  expect(searchStr).toContain("not_category=A&not_category=B");
  expect(new URLSearchParams(searchStr).getAll("not_category")).toEqual(["A", "B"]);
});

test("spells a category slug with the separator it carries", async () => {
  // A colon is legal in a query as it stands, so the serializer puts back the one a form
  // submission would escape: a slug reads in the address bar the way it reads everywhere
  // else. It is the one escape a slug can still produce, every other character in one
  // being carried raw - and it arrives whole typed either way, a slug being one category
  // and not two, so neither the serializer nor validateSearch may split it.
  const router = renderAppAt("/?category=settlement%3Aalice&category=car");
  await screen.findByRole("table", { name: "Expenses" });
  const searchStr = router.state.location.searchStr;
  expect(searchStr).toContain("category=settlement:alice&category=car");
  expect(searchStr).not.toContain("%3A");
  expect(new URLSearchParams(searchStr).getAll("category")).toEqual([
    "settlement:alice",
    "car",
  ]);
});

test("escapes a value that holds the separator's own escape", async () => {
  // The one value putting the colon back could damage: a value reading "%3A" is
  // serialized as "%253A", which holds no "%3A" to replace, and still parses back as the
  // text it was. No slug reads that way, so this is a hand-typed URL - which the
  // serializer carries as the opaque text it carries every value as.
  const router = renderAppAt("/?category=A%253AB");
  await screen.findByRole("table", { name: "Expenses" });
  expect(router.state.location.searchStr).toContain("category=A%253AB");
  expect(router.state.location.search.category).toBe("A%3AB");
});

test("reads every parameter as the string it was typed", async () => {
  // The router's own parser would make a number of this, which validateSearch would then
  // replace with the default; passed through as typed it reaches the backend, whose 422
  // is the one place the form is decided.
  const router = renderAppAt("/?from_date=2026");
  await screen.findByRole("table", { name: "Expenses" });
  expect(router.state.location.search.from_date).toBe("2026");
});
