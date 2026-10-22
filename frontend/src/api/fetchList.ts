// The request every api module makes: GET the URL, refuse a non-2xx status, and refuse a
// body that is not a collection envelope whose items the guard recognises. Nothing
// validates the response for us, so the shape is checked before it reaches React - a
// numeric amount is a contract violation, not a value to coerce. The path is what the
// errors name; the URL is what is fetched.

// One message, so the three refusals below cannot drift apart.
function unexpected(path: string): Error {
  return new Error(`GET ${path} returned an unexpected payload`);
}

// The envelope alone: a 2xx body that is an object. What it holds is each caller's to
// validate, which is what lets the two below share a request and differ on the keys.
async function requestEnvelope(
  path: string,
  url: string | URL,
  signal?: AbortSignal,
): Promise<object> {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`GET ${path} responded ${String(response.status)}`);
  }
  const payload: unknown = await response.json();
  if (typeof payload !== "object" || payload === null) {
    throw unexpected(path);
  }
  return payload;
}

export async function fetchList<T>(
  path: string,
  url: string | URL,
  isList: (payload: unknown) => payload is T[],
  signal?: AbortSignal,
): Promise<T[]> {
  const payload = await requestEnvelope(path, url, signal);
  // The envelope before the guard, which still validates the array of rows inside it.
  if (!("items" in payload) || !isList(payload.items)) {
    throw unexpected(path);
  }
  return payload.items;
}

// The same envelope read whole, for the one endpoint whose body carries a second key.
// Both halves are validated before either reaches React, and a missing `summary` is a
// refusal rather than an empty one: absent would be indistinguishable from a range that
// genuinely summed nothing.
export async function fetchCollection<T, S>(
  path: string,
  url: string | URL,
  isList: (payload: unknown) => payload is T[],
  isSummary: (payload: unknown) => payload is S[],
  signal?: AbortSignal,
): Promise<{ items: T[]; summary: S[] }> {
  const payload = await requestEnvelope(path, url, signal);
  if (
    !("items" in payload) ||
    !isList(payload.items) ||
    !("summary" in payload) ||
    !isSummary(payload.summary)
  ) {
    throw unexpected(path);
  }
  return { items: payload.items, summary: payload.summary };
}
