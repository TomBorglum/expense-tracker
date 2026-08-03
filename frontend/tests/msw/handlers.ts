import { http, HttpResponse } from "msw";

import { GREETING_PATH } from "../../src/api/greeting";

// The stub payload, written out by hand the same way the backend writes the real one.
// Deliberately not the wording in greeting.json: a passing test then proves the text
// travelled over the request rather than coming from anything baked into the bundle.
export const MOCK_GREETING = "Hello from the stub";

export const handlers = [
  // A path-only pattern, which MSW resolves against location.href - jsdom's origin,
  // the same one src/api/greeting.ts builds its absolute URL from.
  http.get(GREETING_PATH, () => HttpResponse.json({ greeting: MOCK_GREETING })),
];
