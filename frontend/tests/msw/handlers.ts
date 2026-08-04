import { http, HttpResponse } from "msw";

import { GREETING_URL } from "@/api/greeting";

// The stub payload, written out by hand the same way the backend writes the real one.
// Deliberately not the wording the backend serves: a passing test then proves the text
// travelled over the request rather than coming from anything baked into the bundle.
export const MOCK_GREETING = "Hello from the stub";

export const handlers = [
  // The absolute URL, not the path. The request is cross-origin now, and a path-only
  // pattern would resolve against jsdom's origin and never match it.
  http.get(GREETING_URL, () => HttpResponse.json({ greeting: MOCK_GREETING })),
];
