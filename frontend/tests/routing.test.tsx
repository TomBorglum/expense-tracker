import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryHistory, RouterProvider } from "@tanstack/react-router";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { createAppRouter } from "@/router";

import { MOCK_GREETING } from "./msw/handlers";

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

test("serves the greeting at the root path", async () => {
  renderAppAt("/");
  const heading = await screen.findByRole("heading", { level: 1 });
  expect(heading.textContent).toBe(MOCK_GREETING);
});

test("serves the expenses table at /expenses", async () => {
  renderAppAt("/expenses");
  const table = await screen.findByRole("table", { name: "Expenses" });
  expect(table.tagName).toBe("TABLE");
});

test("navigates from the greeting to the expenses page through the nav", async () => {
  renderAppAt("/");
  // Awaited, not queried synchronously: the router resolves its first match before it
  // renders anything at all, so the nav does not exist on the first tick.
  const link = await screen.findByRole("link", { name: "Expenses" });
  // fireEvent rather than user-event, which is not a dependency here.
  fireEvent.click(link);
  const table = await screen.findByRole("table", { name: "Expenses" });
  expect(table.tagName).toBe("TABLE");
});
