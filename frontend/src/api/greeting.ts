import { queryOptions } from "@tanstack/react-query";

// The wire contract, written out by hand. The backend builds the same payload by hand
// in backend/src/expense_tracker/__init__.py; create_app() sets openapi_url=None, so
// there is no schema to generate either side from and the two declarations are kept in
// step deliberately. Change them together.
export interface Greeting {
  greeting: string;
}

// The one string both stacks have to agree on. backend/tests/test_app.py greps the
// committed bundle for it, so a rename here fails the Python suite until the bundle is
// rebuilt and the route renamed too.
export const GREETING_PATH = "/api/greeting";

function isGreeting(payload: unknown): payload is Greeting {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "greeting" in payload &&
    typeof payload.greeting === "string"
  );
}

export async function fetchGreeting(signal?: AbortSignal): Promise<Greeting> {
  // Resolved against the origin rather than passed as a bare path: the page and the
  // API are same-origin in the browser, and under vitest this runs on Node's fetch,
  // which rejects a URL with no host.
  const response = await fetch(new URL(GREETING_PATH, window.location.origin), {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`GET ${GREETING_PATH} responded ${String(response.status)}`);
  }
  const payload: unknown = await response.json();
  // Nothing validates the response for us, so the shape is checked before it reaches
  // React rather than trusting the cast that `response.json()` would otherwise imply.
  if (!isGreeting(payload)) {
    throw new Error(`GET ${GREETING_PATH} returned an unexpected payload`);
  }
  return payload;
}

export const greetingQueryOptions = queryOptions({
  queryKey: ["greeting"],
  queryFn: ({ signal }) => fetchGreeting(signal),
});
