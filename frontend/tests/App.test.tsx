import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { expect, test } from "vitest";

import { GREETING_URL } from "@/api/greeting";
import App from "@/App";

import { MOCK_GREETING } from "./msw/handlers";
import { server } from "./msw/server";

function renderApp() {
  // A fresh client per test, so nothing is served out of a cache another test filled,
  // and retry off, so the failure cases settle immediately instead of waiting out a
  // backoff. main.tsx configures the real client separately.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );
}

test("renders the greeting served by the API", async () => {
  renderApp();
  // Reaching the heading at all means the request went to GREETING_URL: setup.ts runs
  // msw with onUnhandledRequest "error", so a base-URL mismatch fails here rather than
  // escaping to the network.
  const heading = await screen.findByRole("heading", { level: 1 });
  expect(heading.textContent).toBe(MOCK_GREETING);
});

test("shows a status while the request is in flight", () => {
  renderApp();
  expect(screen.getByRole("status").textContent).toBe("Loading...");
});

test("shows an alert when the endpoint fails", async () => {
  server.use(http.get(GREETING_URL, () => new HttpResponse(null, { status: 500 })));
  renderApp();
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the greeting.");
});

test("shows an alert when the payload does not match the contract", async () => {
  // Nothing generates a client from a schema here, so the guard in src/api/greeting.ts
  // is the only thing between a drifted backend and a render that reads undefined.
  server.use(http.get(GREETING_URL, () => HttpResponse.json({})));
  renderApp();
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toBe("Could not load the greeting.");
});
