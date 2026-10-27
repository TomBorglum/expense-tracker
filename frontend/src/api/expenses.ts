import { queryOptions } from "@tanstack/react-query";

import { type CategoryDefault } from "./categories";
import { fetchList } from "./fetchList";

// The wire contract, written out by hand. The backend builds the same payload by hand as
// ExpensePayload in backend/src/expense_tracker/__init__.py; create_app() sets
// openapi_url=None, so there is no schema to generate either side from and the two
// declarations are kept in step deliberately. Change them together. Every field is a
// string, amount included: JSON has no decimal type, so a float round trip is how a
// total drifts by a cent.
export interface Expense {
  amount: string;
  currency: string;
  date: string;
  category: string;
  key: string;
}

// The path both stacks have to agree on. Nothing checks that agreement automatically
// now that the two build independently - a rename here needs the same rename in the
// backend's route, and the failure shows up as a 404 at runtime.
export const EXPENSES_PATH = "/api/expenses";

// Resolved once against the configured API origin. Exported because the mocks have to
// match this exact absolute URL: msw resolves a path-only handler against the document
// location, which under jsdom is not the API's origin, so such a handler would simply
// never fire.
export const EXPENSES_URL = new URL(EXPENSES_PATH, import.meta.env.VITE_API_BASE_URL)
  .href;

function isExpense(payload: unknown): payload is Expense {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "amount" in payload &&
    typeof payload.amount === "string" &&
    "currency" in payload &&
    typeof payload.currency === "string" &&
    "date" in payload &&
    typeof payload.date === "string" &&
    "category" in payload &&
    typeof payload.category === "string" &&
    "key" in payload &&
    typeof payload.key === "string"
  );
}

// every() rather than a loop over an index: Array.isArray narrows an unknown to any[],
// and every() hands each element to isExpense as unknown instead of reaching into an
// any.
function isExpenseList(payload: unknown): payload is Expense[] {
  return Array.isArray(payload) && payload.every(isExpense);
}

// The query half of the same contract: six optional parameters on the backend, the
// first three always sent from here. An empty value is malformed to the backend rather
// than an absent one, so there is no "everything" request to fall back to. The three
// category keys are the exception: all absent is every category on both sides, neither
// list is ever empty, and the flag is sent only where the backend would otherwise read
// the root the other way - so the query key holds no dead entry. They are required and
// `| undefined` rather than optional: this type is the URL search too, and a key left out
// of a navigate keeps the value it had rather than clearing it.
export interface ExpensesQuery {
  currency: string;
  from_date: string;
  to_date: string;
  category: string[] | undefined;
  not_category: string[] | undefined;
  category_default: CategoryDefault | undefined;
}

export async function fetchExpenses(
  query: ExpensesQuery,
  signal?: AbortSignal,
): Promise<Expense[]> {
  // Built per call rather than folded into EXPENSES_URL, which stays the bare endpoint
  // the msw handlers bind to.
  const url = new URL(EXPENSES_URL);
  url.searchParams.set("currency", query.currency);
  url.searchParams.set("from_date", query.from_date);
  url.searchParams.set("to_date", query.to_date);
  // Appended rather than set: the backend reads either key once per value.
  for (const slug of query.category ?? []) {
    url.searchParams.append("category", slug);
  }
  for (const slug of query.not_category ?? []) {
    url.searchParams.append("not_category", slug);
  }
  if (query.category_default !== undefined) {
    // Set only where it is needed, the way group_by is: an absent flag is what lets the
    // backend read the root off the selected list, which is the common case.
    url.searchParams.set("category_default", query.category_default);
  }
  return fetchList(EXPENSES_PATH, url, isExpenseList, signal);
}

// A factory rather than a constant, so each set of parameters is its own cache entry.
// That is also what puts the table back into its pending branch on a change, instead of
// showing the previous currency's amounts under the new code or the previous month's
// rows under new dates. TanStack Query hashes the object deterministically, so the key
// needs no element per parameter.
export function expensesQueryOptions(query: ExpensesQuery) {
  return queryOptions({
    queryKey: ["expenses", query],
    queryFn: ({ signal }) => fetchExpenses(query, signal),
  });
}
