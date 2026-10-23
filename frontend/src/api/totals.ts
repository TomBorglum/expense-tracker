import { queryOptions } from "@tanstack/react-query";

import { fetchCollection } from "./fetchList";

// The wire contract, written out by hand, the same way expenses.ts writes out its own.
// The backend builds the same payload as PeriodTotalPayload in
// backend/src/expense_tracker/__init__.py; there is no schema to generate either side
// from, so the two declarations are kept in step deliberately. Change them together.
//
// The first three fields are on every row. The last three are dumped with exclude_none,
// so each is present with a value or absent altogether - never null and never "". An
// absent amount means the period holds no expenses, which is not the same as a period of
// credits that netted to "0.00"; such a period carries the span and nothing else.
export interface PeriodTotal {
  period: string;
  from_date: string;
  to_date: string;
  amount?: string;
  currency?: string;
  category?: string;
}

// The other half of the same body, built as SummaryPayload: one entry per currency,
// holding the mean of its period totals over the whole calendar the rows span. Neither
// key is ever absent, unlike a row's - an entry exists only for a currency that has
// expenses - so both are required here and the guard rejects a missing one. It is the
// same whether or not the request grouped, which is why the stat reads it from the
// ungrouped request the table already makes.
export interface RangeAverage {
  currency: string;
  average: string;
}

// What the totals body is, both halves together.
export interface TotalsCollection {
  items: PeriodTotal[];
  summary: RangeAverage[];
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

function isRangeAverage(payload: unknown): payload is RangeAverage {
  return (
    typeof payload === "object" &&
    payload !== null &&
    // Present and a string, never absent and never a number: the asymmetry with a row's
    // optional keys is the contract, so an absent key is a refusal here.
    "currency" in payload &&
    typeof payload.currency === "string" &&
    "average" in payload &&
    typeof payload.average === "string"
  );
}

function isRangeAverageList(payload: unknown): payload is RangeAverage[] {
  return Array.isArray(payload) && payload.every(isRangeAverage);
}

// The query half of the same contract. group_by and category are optional on both sides
// and mean the same thing by their absence: sum the categories together and leave the
// field off the row, and draw from every category rather than the ones named.
export interface TotalsQuery {
  currency: string;
  from_date: string;
  to_date: string;
  group_by?: typeof CATEGORY_GROUPING;
  category?: string[];
}

export async function fetchTotals(
  query: TotalsQuery,
  signal?: AbortSignal,
): Promise<TotalsCollection> {
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
  // Appended rather than set: the backend reads the key once per value.
  for (const name of query.category ?? []) {
    url.searchParams.append("category", name);
  }
  return fetchCollection(
    TOTALS_PATH,
    url,
    isPeriodTotalList,
    isRangeAverageList,
    signal,
  );
}

// The same query with the grouping dropped, which is what both the table's period bands
// and the range stat request. Content-hashed into the same queryKey, so the two read one
// cache entry rather than fetching a copy each.
export function ungrouped(query: TotalsQuery): TotalsQuery {
  // Deleted rather than set to undefined, so the key is gone from the object and not
  // merely empty in it: the hash drops an undefined value, but a reader of the key does
  // not have to know that.
  const range: TotalsQuery = { ...query };
  delete range.group_by;
  return range;
}

// Module-level, never inline: react-query re-runs select when the function's reference
// changes, so an arrow written at the call site would recompute on every render. Each
// component subscribes to its own half and re-renders only when that half changes, the
// cache still holding the whole body.
export const selectItems = (data: TotalsCollection): PeriodTotal[] => data.items;
export const selectSummary = (data: TotalsCollection): RangeAverage[] => data.summary;

// A factory for the reason expensesQueryOptions is one: each set of parameters is its own
// cache entry, which is what puts the view back into its pending branch on a change
// instead of showing the previous range's sums under new dates.
export function totalsQueryOptions(query: TotalsQuery) {
  return queryOptions({
    queryKey: ["totals", query],
    queryFn: ({ signal }) => fetchTotals(query, signal),
  });
}
