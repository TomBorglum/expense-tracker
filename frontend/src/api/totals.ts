import { queryOptions } from "@tanstack/react-query";

// The wire contract, written out by hand, the same way expenses.ts writes out its own.
// The backend builds the same payload as PeriodTotalPayload in
// backend/src/expense_tracker/__init__.py; there is no schema to generate either side
// from, so the two declarations are kept in step deliberately. Change them together.
//
// The first three fields are on every row. The last three are dumped with exclude_none,
// so each is present with a value or absent altogether - never null and never "". An
// absent amount means the period holds no expenses, which is not the same as a period of
// refunds that netted to "0.00".
export interface PeriodTotal {
  period: string;
  from_date: string;
  to_date: string;
  amount?: string;
  currency?: string;
  category?: string;
}

export const TOTALS_PATH = "/api/expenses/totals";

// Exported for the same reason EXPENSES_URL is: msw resolves a path-only handler against
// the document location, which under jsdom is not the API's origin.
export const TOTALS_URL = new URL(TOTALS_PATH, import.meta.env.VITE_API_BASE_URL).href;

// The only member of the backend's Period enum, and the only one of its Grouping enum.
// Sent as a constant rather than picked: a control offering one value is dead UI, and the
// payload field is the grain-neutral `period`, so a second grain renames nothing here.
export const PERIOD = "month";
export const CATEGORY_GROUPING = "category";

function isPeriodTotal(payload: unknown): payload is PeriodTotal {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "period" in payload &&
    typeof payload.period === "string" &&
    "from_date" in payload &&
    typeof payload.from_date === "string" &&
    "to_date" in payload &&
    typeof payload.to_date === "string" &&
    // Absent or a string, never null and never a number: `in` is what tells an absent
    // key from a present empty one, and it is the narrowing that types the read.
    (!("amount" in payload) || typeof payload.amount === "string") &&
    (!("currency" in payload) || typeof payload.currency === "string") &&
    (!("category" in payload) || typeof payload.category === "string")
  );
}

// every() rather than a loop over an index, for the reason isExpenseList gives: it hands
// each element on as unknown instead of reaching into an any.
function isPeriodTotalList(payload: unknown): payload is PeriodTotal[] {
  return Array.isArray(payload) && payload.every(isPeriodTotal);
}

// The query half of the same contract. group_by is optional on both sides and means the
// same thing by its absence: sum the categories together and leave the field off the row.
export interface TotalsQuery {
  currency: string;
  from_date: string;
  to_date: string;
  group_by?: typeof CATEGORY_GROUPING;
}

export async function fetchTotals(
  query: TotalsQuery,
  signal?: AbortSignal,
): Promise<PeriodTotal[]> {
  const url = new URL(TOTALS_URL);
  // Always sent: the backend refuses an absent period rather than defaulting one.
  url.searchParams.set("period", PERIOD);
  url.searchParams.set("currency", query.currency);
  url.searchParams.set("from_date", query.from_date);
  url.searchParams.set("to_date", query.to_date);
  if (query.group_by !== undefined) {
    // Set only when grouping. An empty group_by is malformed to the backend, so the
    // ungrouped request is the one that omits the parameter altogether.
    url.searchParams.set("group_by", query.group_by);
  }
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`GET ${TOTALS_PATH} responded ${String(response.status)}`);
  }
  const payload: unknown = await response.json();
  if (!isPeriodTotalList(payload)) {
    throw new Error(`GET ${TOTALS_PATH} returned an unexpected payload`);
  }
  return payload;
}

// A factory for the reason expensesQueryOptions is one: each set of parameters is its own
// cache entry, which is what puts the view back into its pending branch on a change
// instead of showing the previous range's sums under new dates.
export function totalsQueryOptions(query: TotalsQuery) {
  return queryOptions({
    queryKey: ["totals", query],
    queryFn: ({ signal }) => fetchTotals(query, signal),
  });
}
