import { createRouter, type RouterHistory } from "@tanstack/react-router";

import { routeTree } from "./routeTree.gen";

// A key that repeats once per value, the form an HTML form submits and the backend's
// list[str] reads. The router's own serializer writes a list as a JSON array and coerces
// "2026" to a number on the way in, and its parseSearchWith / stringifySearchWith
// helpers work one value at a time, so neither half could spell this.
function parseSearch(searchStr: string): Record<string, string | string[]> {
  const params = new URLSearchParams(searchStr);
  const search: Record<string, string | string[]> = {};
  for (const key of new Set(params.keys())) {
    const values = params.getAll(key);
    search[key] = values.length === 1 ? values[0] : values;
  }
  return search;
}

function stringifySearch(search: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(search)) {
    for (const item of Array.isArray(value) ? value : [value]) {
      if (item !== undefined) {
        params.append(key, String(item));
      }
    }
  }
  // URLSearchParams escapes every character outside the unreserved set, the category
  // separator among them; a colon is legal in a query, so it goes back in. It is the one
  // escape a category slug can produce - every other character in one is unreserved -
  // so this line is what keeps a category URL free of percent-encoding. A value holding
  // the text "%3A" was escaped to "%253A", which this does not match.
  const text = params.toString().replaceAll("%3A", ":");
  return text === "" ? "" : `?${text}`;
}

// A factory rather than a module-level singleton, so the tests build their own router
// over a memory history instead of sharing navigation state between them.
export function createAppRouter(history?: RouterHistory) {
  return createRouter({ routeTree, history, parseSearch, stringifySearch });
}

// Without this declaration Link, useNavigate and useSearch have no type safety, and a
// path that matches no route is accepted rather than rejected at build time.
declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
