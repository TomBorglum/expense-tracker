import { queryOptions } from "@tanstack/react-query";

import { fetchList } from "./fetchList";

// The wire contract, written out by hand, the same way expenses.ts writes out its own.
// The backend builds the same payload as CategoryPayload in
// backend/src/expense_tracker/__init__.py; there is no schema to generate either side
// from, so the two declarations are kept in step deliberately. Change them together.
export interface Category {
  category: string;
}

export const CATEGORIES_PATH = "/api/expenses/categories";

// Exported for the same reason EXPENSES_URL is: msw resolves a path-only handler against
// the document location, which under jsdom is not the API's origin.
export const CATEGORIES_URL = new URL(
  CATEGORIES_PATH,
  import.meta.env.VITE_API_BASE_URL,
).href;

function isCategory(payload: unknown): payload is Category {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "category" in payload &&
    typeof payload.category === "string"
  );
}

function isCategoryList(payload: unknown): payload is Category[] {
  return Array.isArray(payload) && payload.every(isCategory);
}

export function fetchCategories(signal?: AbortSignal): Promise<Category[]> {
  return fetchList(CATEGORIES_PATH, CATEGORIES_URL, isCategoryList, signal);
}

// The names as the backend sends them: once each and in name order already, so nothing
// here sorts or deduplicates a second time.
export function categoryNames(categories: Category[]): string[] {
  return categories.map((item) => item.category);
}

// The ?category= filter as validateSearch reads it off the URL: one value arrives as a
// string and several as an array, and either becomes the list the query sends. Absent,
// or nothing usable, is undefined - no filter, which is what an absent key means on the
// wire too. An empty string is kept: the backend refuses it with a 422, the way it
// refuses an empty ?currency=, and correcting it here would put that rule in two places.
export function categoryFilter(value: unknown): string[] | undefined {
  const values = Array.isArray(value) ? value : [value];
  const names = values.filter((item): item is string => typeof item === "string");
  return names.length === 0 ? undefined : names;
}

export const categoriesQueryOptions = queryOptions({
  queryKey: ["categories"],
  queryFn: ({ signal }) => fetchCategories(signal),
});
