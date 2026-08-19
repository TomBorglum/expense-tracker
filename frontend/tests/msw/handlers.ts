import { http, HttpResponse } from "msw";

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

export const handlers = [
  // The absolute URL, not the path. The request is cross-origin now, and a path-only
  // pattern would resolve against jsdom's origin and never match it.
  http.get(EXPENSES_URL, () => HttpResponse.json(MOCK_EXPENSES)),
];
