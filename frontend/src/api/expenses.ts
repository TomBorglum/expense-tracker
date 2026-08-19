import { queryOptions } from "@tanstack/react-query";

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
  details: string;
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
    "details" in payload &&
    typeof payload.details === "string"
  );
}

// every() rather than a loop over an index: Array.isArray narrows an unknown to any[],
// and every() hands each element to isExpense as unknown instead of reaching into an
// any.
function isExpenseList(payload: unknown): payload is Expense[] {
  return Array.isArray(payload) && payload.every(isExpense);
}

export async function fetchExpenses(signal?: AbortSignal): Promise<Expense[]> {
  const response = await fetch(EXPENSES_URL, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`GET ${EXPENSES_PATH} responded ${String(response.status)}`);
  }
  const payload: unknown = await response.json();
  // Nothing validates the response for us, so the shape is checked before it reaches
  // React. A numeric amount is a contract violation, not a value to coerce.
  if (!isExpenseList(payload)) {
    throw new Error(`GET ${EXPENSES_PATH} returned an unexpected payload`);
  }
  return payload;
}

export const expensesQueryOptions = queryOptions({
  queryKey: ["expenses"],
  queryFn: ({ signal }) => fetchExpenses(signal),
});
