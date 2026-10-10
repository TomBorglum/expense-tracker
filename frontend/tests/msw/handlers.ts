import { http, HttpResponse } from "msw";

import { CATEGORIES_URL, type Category } from "@/api/categories";
import { CURRENCIES_URL, type CurrencyRate } from "@/api/currencies";
import { type Expense, EXPENSES_URL } from "@/api/expenses";
import { type PeriodTotal, TOTALS_URL } from "@/api/totals";

// Oldest first, the order the API sends. Deliberately not values the loader produces -
// another currency, dates from another decade - so a passing test proves they travelled
// over the request. The first row is a negative amount with empty details, both of
// which the contract allows.
export const MOCK_EXPENSES: Expense[] = [
  {
    amount: "-4.20",
    currency: "GBP",
    date: "2000-01-02",
    category: "Other stub category",
    details: "",
  },
  {
    amount: "13.37",
    currency: "EUR",
    date: "2001-02-03",
    category: "Stub category",
    details: "Stub details",
  },
];

// Two of the four rows are noise the selector must drop: SEK -> DKK points the wrong way
// and is never inverted, and the duplicate DKK -> USD is one option, not two. Rates the
// loader would refuse are fine here - nothing in the frontend parses rates.tsv.
export const MOCK_RATES: CurrencyRate[] = [
  { from_currency: "DKK", to_currency: "USD", exchange_rate: "0.123456" },
  { from_currency: "DKK", to_currency: "EUR", exchange_rate: "7.654321" },
  { from_currency: "SEK", to_currency: "DKK", exchange_rate: "0.500000" },
  { from_currency: "DKK", to_currency: "USD", exchange_rate: "0.123456" },
];

// A dense calendar, oldest first: three periods spanning a gap the middle one records
// nothing in. That row carries its span and no amount at all - the keys are absent, not
// null, which is what the guard and the "None recorded" branch are written against.
export const MOCK_TOTALS: PeriodTotal[] = [
  {
    period: "2001-01",
    from_date: "2001-01-01",
    to_date: "2001-01-31",
    amount: "11.00",
    currency: "EUR",
  },
  { period: "2001-02", from_date: "2001-02-01", to_date: "2001-02-28" },
  {
    period: "2001-03",
    from_date: "2001-03-01",
    to_date: "2001-03-31",
    amount: "30.00",
    currency: "EUR",
  },
];

// The same three periods split by category, which is the payload ?group_by=category
// answers with. The amounts add up to the ungrouped ones above, because that is the
// property the view relies on when it takes its subtotal from the other request.
export const MOCK_CATEGORY_TOTALS: PeriodTotal[] = [
  {
    period: "2001-01",
    from_date: "2001-01-01",
    to_date: "2001-01-31",
    amount: "11.00",
    currency: "EUR",
    category: "Stub category",
  },
  { period: "2001-02", from_date: "2001-02-01", to_date: "2001-02-28" },
  {
    period: "2001-03",
    from_date: "2001-03-01",
    to_date: "2001-03-31",
    amount: "12.50",
    currency: "EUR",
    category: "Stub category",
  },
  {
    period: "2001-03",
    from_date: "2001-03-01",
    to_date: "2001-03-31",
    amount: "17.50",
    currency: "EUR",
    category: "Other stub category",
  },
  {
    period: "2001-03",
    from_date: "2001-03-01",
    to_date: "2001-03-31",
    amount: "0.00",
    currency: "EUR",
    category: "Stub category:Nested stub",
  },
];

// The two names the mock expenses carry, a third nothing is filed under, and one path
// below the second, in the path order the backend sends - so a test can tick one and
// tell it from the rest, and the picker has a tree to build rather than a list.
export const MOCK_CATEGORIES: Category[] = [
  { category: "Other stub category", name: "Other stub category" },
  { category: "Stub category", name: "Stub category" },
  {
    category: "Stub category:Nested stub",
    name: "Nested stub",
    parent: "Stub category",
  },
  { category: "Third stub category", name: "Third stub category" },
];

// Every collection body is an object holding its rows, so a mock has to be one too.
// Spelled here once rather than at each stub: a mock that answered a bare array would
// make fetchList throw, and the failure would read as a guard bug.
export function collection(items: unknown): Response {
  return HttpResponse.json({ items });
}

export const handlers = [
  // The absolute URLs, not the paths. The requests are cross-origin now, and a path-only
  // pattern would resolve against jsdom's origin and never match them.
  http.get(EXPENSES_URL, () => collection(MOCK_EXPENSES)),
  // Registered for every test, not only the ones about the selector: setup.ts errors on
  // an unstubbed request, and anything mounting the page asks for the rates.
  http.get(CURRENCIES_URL, () => collection(MOCK_RATES)),
  // Registered for the same reason: both pages ask for the category list on mount.
  http.get(CATEGORIES_URL, () => collection(MOCK_CATEGORIES)),
  // Matched ahead of nothing: msw compares whole paths, so /api/expenses does not catch
  // /api/expenses/totals despite being its prefix. The totals view makes both requests
  // whenever it is grouped, and they differ only by this parameter.
  http.get(TOTALS_URL, ({ request }) =>
    collection(
      new URL(request.url).searchParams.get("group_by") === null
        ? MOCK_TOTALS
        : MOCK_CATEGORY_TOTALS,
    ),
  ),
];
