import { queryOptions } from "@tanstack/react-query";

// The wire contract, written out by hand. The backend builds the same payload by hand
// in backend/src/expense_tracker/__init__.py; create_app() sets openapi_url=None, so
// there is no schema to generate either side from and the two declarations are kept in
// step deliberately. Change them together.
export interface Greeting {
  greeting: string;
}

// The path both stacks have to agree on. Nothing checks that agreement automatically
// now that the two build independently - a rename here needs the same rename in the
// backend's route, and the failure shows up as a 404 at runtime.
export const GREETING_PATH = "/api/greeting";

// Resolved once against the configured API origin. Exported because the mocks have to
// match this exact absolute URL: msw resolves a path-only handler against the document
// location, which under jsdom is not the API's origin, so such a handler would simply
// never fire. msw ships no baseURL option by design and recommends a shared constant
// built this way instead.
export const GREETING_URL = new URL(GREETING_PATH, import.meta.env.VITE_API_BASE_URL)
  .href;

function isGreeting(payload: unknown): payload is Greeting {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "greeting" in payload &&
    typeof payload.greeting === "string"
  );
}

export async function fetchGreeting(signal?: AbortSignal): Promise<Greeting> {
  // The API is a separate app on its own origin, so this is a genuine cross-origin
  // request and only succeeds because the backend allows it (CORSMiddleware in
  // create_app).
  const response = await fetch(GREETING_URL, {
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
