import { queryOptions } from "@tanstack/react-query";

import { fetchList } from "./fetchList";

// The wire contract, written out by hand, the same way expenses.ts writes out its own.
// The backend builds the same payload as CategoryPayload in
// backend/src/expense_tracker/__init__.py; there is no schema to generate either side
// from, so the two declarations are kept in step deliberately. Change them together.
export interface Category {
  // The whole colon-separated path, which is what ?category= takes.
  category: string;
  // Its last level, and the path above it - absent on a depth-1 category, which has
  // none. The two are why nothing here splits a path: the separator is the backend's.
  name: string;
  parent?: string;
}

// The query half of the same pair, and only the half this side sends: the picker asks
// for a bounded tree in one request, never for a single generation, so the backend's
// from_level has no caller here. A string, because every query parameter on that side is
// one, and required rather than optional for the reason ExpensesQuery's three are: this
// client always says how deep it wants, so an absent one is no request it makes.
export interface CategoriesQuery {
  to_level: string;
}

// What the picker asks for: the tree down to three levels in one request, so opening it
// costs one round trip and reading it costs none. Not a declared-twice pair with the
// backend's MAX_LEVEL - any value inside that cap is a valid request.
export const CATEGORY_LEVELS: CategoriesQuery = { to_level: "3" };

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
    typeof payload.category === "string" &&
    "name" in payload &&
    typeof payload.name === "string" &&
    // Absent or a string, never null: `in` is what tells a root from a child, the way
    // isPeriodTotal tells a period holding nothing from one that netted to 0.00.
    (!("parent" in payload) || typeof payload.parent === "string")
  );
}

function isCategoryList(payload: unknown): payload is Category[] {
  return Array.isArray(payload) && payload.every(isCategory);
}

export function fetchCategories(
  query: CategoriesQuery,
  signal?: AbortSignal,
): Promise<Category[]> {
  const url = new URL(CATEGORIES_URL);
  url.searchParams.set("to_level", query.to_level);
  return fetchList(CATEGORIES_PATH, url, isCategoryList, signal);
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

// A factory rather than the constant it was, for the reason expensesQueryOptions is
// one: each range is its own cache entry, and an object inside a key is hashed by value
// rather than by identity.
export function categoriesQueryOptions(query: CategoriesQuery) {
  return queryOptions({
    queryKey: ["categories", query],
    queryFn: ({ signal }) => fetchCategories(query, signal),
  });
}
