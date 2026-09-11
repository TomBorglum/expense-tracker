import { categoryFilter } from "./api/categories";
import { BASE_CURRENCY } from "./api/currencies";
import { type ExpensesQuery } from "./api/expenses";
import { currentYear } from "./dates";

// The four parameters both views read, and what crossing between them brings along. The
// nav links in __root.tsx carry no search of their own, so without this the currency,
// the range and the categories are picked again on every switch. group_by is deliberately
// not here - it is declared on /totals alone, and the expenses view means nothing by it.
// A list rather than the middleware itself, which is typed against the route it sits in.
export const SHARED_SEARCH_KEYS: (keyof ExpensesQuery)[] = [
  "currency",
  "from_date",
  "to_date",
  "category",
];

// Supplies the default for an absent parameter and nothing else. A malformed code, date
// or category is handed on to the backend, which refuses it with a 422; re-checking any
// here would put the pattern in conversion.py, date_range.py or category_filter.py in a
// second place to drift from. An absent bound becomes the first or last day of the
// current year, the same on both views so that a switch between them changes nothing;
// it reads the clock, which is why both page tests pin it.
export function sharedSearch(search: Record<string, unknown>): ExpensesQuery {
  const year = currentYear();
  return {
    currency: typeof search.currency === "string" ? search.currency : BASE_CURRENCY,
    from_date: typeof search.from_date === "string" ? search.from_date : year.from,
    to_date: typeof search.to_date === "string" ? search.to_date : year.to,
    category: categoryFilter(search.category),
  };
}
