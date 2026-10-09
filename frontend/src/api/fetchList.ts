// The request every api module makes: GET the URL, refuse a non-2xx status, and refuse a
// body that is not a collection envelope whose items the guard recognises. Nothing
// validates the response for us, so the shape is checked before it reaches React - a
// numeric amount is a contract violation, not a value to coerce. The path is what the
// errors name; the URL is what is fetched.
export async function fetchList<T>(
  path: string,
  url: string | URL,
  isList: (payload: unknown) => payload is T[],
  signal?: AbortSignal,
): Promise<T[]> {
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`GET ${path} responded ${String(response.status)}`);
  }
  const payload: unknown = await response.json();
  // The envelope before the guard, which still validates the array of rows inside it.
  if (
    typeof payload !== "object" ||
    payload === null ||
    !("items" in payload) ||
    !isList(payload.items)
  ) {
    throw new Error(`GET ${path} returned an unexpected payload`);
  }
  return payload.items;
}
