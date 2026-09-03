import { http, HttpResponse } from "msw";

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
];

export const handlers = [
  // The absolute URLs, not the paths. The requests are cross-origin now, and a path-only
  // pattern would resolve against jsdom's origin and never match them.
  http.get(EXPENSES_URL, () => HttpResponse.json(MOCK_EXPENSES)),
  // Registered for every test, not only the ones about the selector: setup.ts errors on
  // an unstubbed request, and anything mounting the page asks for the rates.
  http.get(CURRENCIES_URL, () => HttpResponse.json(MOCK_RATES)),
  // Matched ahead of nothing: msw compares whole paths, so /api/expenses does not catch
  // /api/expenses/totals despite being its prefix. The totals view makes both requests
  // whenever it is grouped, and they differ only by this parameter.
  http.get(TOTALS_URL, ({ request }) =>
    HttpResponse.json(
      new URL(request.url).searchParams.get("group_by") === null
        ? MOCK_TOTALS
        : MOCK_CATEGORY_TOTALS,
    ),
  ),
];
