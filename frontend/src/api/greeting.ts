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

// Absolute URLs against the configured API origin, preserving any path the origin
// carries. A bare `new URL("/api/greeting", base)` resolves the leading slash against
// the base's ORIGIN and discards the rest, so a VITE_API_BASE_URL of
// https://host/v1 would silently become https://host/api/greeting. Appending to a base
// normalised to end in "/", with the leading slash taken off the path, is what keeps a
// prefixed deployment working.
// Exported for tests/api/greeting.test.ts, the same reason GREETING_URL below is: a
// prefixed or trailing-slash base is a deployment concern that nothing else in the suite
// would ever exercise, and the failure it guards against is silent.
export function apiUrl(path: string): string {
  const base = import.meta.env.VITE_API_BASE_URL;
  // vite inlines this at build time, so an unset or empty value is a misconfigured
  // build rather than something to recover from at runtime. It has to fail either way -
  // `new URL(path, "")` throws too - but it throws an opaque TypeError, from module
  // scope, which reaches the page as a blank screen with no error branch to catch it.
  // Naming the variable is the whole improvement.
  if (!base) {
    throw new Error(
      "VITE_API_BASE_URL is not set; frontend/.env holds the development value",
    );
  }
  return new URL(
    path.startsWith("/") ? path.slice(1) : path,
    base.endsWith("/") ? base : `${base}/`,
  ).href;
}

// Resolved once. Exported because the mocks have to match this exact absolute URL: msw
// resolves a path-only handler against the document location, which under jsdom is not
// the API's origin, so such a handler would simply never fire. msw ships no baseURL
// option by design and recommends a shared constant built this way instead.
export const GREETING_URL = apiUrl(GREETING_PATH);

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
