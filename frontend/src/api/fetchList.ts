// The request every api module makes: GET the URL, refuse a non-2xx status, and refuse a
// body the guard does not recognise. Nothing validates the response for us, so the shape
// is checked before it reaches React - a numeric amount is a contract violation, not a
// value to coerce. The path is what the errors name; the URL is what is fetched.
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
  if (!isList(payload)) {
    throw new Error(`GET ${path} returned an unexpected payload`);
  }
  return payload;
}
