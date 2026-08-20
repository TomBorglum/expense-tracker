import { http, HttpResponse } from "msw";

import { CURRENCIES_URL, type CurrencyRate } from "@/api/currencies";
import { type Expense, EXPENSES_URL } from "@/api/expenses";

// Newest first, the order the API sends. Deliberately not values the loader produces -
// another currency, dates from another decade - so a passing test proves they travelled
// over the request. The second row is a negative amount with empty details, both of
// which the contract allows.
export const MOCK_EXPENSES: Expense[] = [
  {
    amount: "13.37",
    currency: "EUR",
    date: "2001-02-03",
    category: "Stub category",
    details: "Stub details",
  },
  {
    amount: "-4.20",
    currency: "GBP",
    date: "2000-01-02",
    category: "Other stub category",
    details: "",
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

export const handlers = [
  // The absolute URLs, not the paths. The requests are cross-origin now, and a path-only
  // pattern would resolve against jsdom's origin and never match them.
  http.get(EXPENSES_URL, () => HttpResponse.json(MOCK_EXPENSES)),
  // Registered for every test, not only the ones about the selector: setup.ts errors on
  // an unstubbed request, and anything mounting the page asks for the rates.
  http.get(CURRENCIES_URL, () => HttpResponse.json(MOCK_RATES)),
];
