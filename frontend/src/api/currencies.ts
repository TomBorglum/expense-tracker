import { queryOptions } from "@tanstack/react-query";

// The wire contract, written out by hand, the same way expenses.ts writes out its own.
// The backend builds the same payload as CurrencyPayload in
// backend/src/expense_tracker/__init__.py; there is no schema to generate either side
// from, so the two declarations are kept in step deliberately. exchange_rate is a string
// for the reason amount is: JSON has no decimal type, and an amount multiplied by a rate
// that made a float round trip is an amount that has drifted.
export interface CurrencyRate {
  from_currency: string;
  to_currency: string;
  exchange_rate: string;
}

// The currency the ledger is kept in, and the one code that needs no rate: the backend
// returns a record whose currency already equals the target before it looks a rate up,
// so this stays selectable against an empty rate table.
export const BASE_CURRENCY = "DKK";

export const CURRENCIES_PATH = "/api/currencies";

// Exported for the same reason EXPENSES_URL is: msw resolves a path-only handler against
// the document location, which under jsdom is not the API's origin.
export const CURRENCIES_URL = new URL(
  CURRENCIES_PATH,
  import.meta.env.VITE_API_BASE_URL,
).href;

function isCurrencyRate(payload: unknown): payload is CurrencyRate {
  return (
    typeof payload === "object" &&
    payload !== null &&
    "from_currency" in payload &&
    typeof payload.from_currency === "string" &&
    "to_currency" in payload &&
    typeof payload.to_currency === "string" &&
    "exchange_rate" in payload &&
    typeof payload.exchange_rate === "string"
  );
}

function isCurrencyRateList(payload: unknown): payload is CurrencyRate[] {
  return Array.isArray(payload) && payload.every(isCurrencyRate);
}

export async function fetchCurrencies(signal?: AbortSignal): Promise<CurrencyRate[]> {
  const response = await fetch(CURRENCIES_URL, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) {
    throw new Error(`GET ${CURRENCIES_PATH} responded ${String(response.status)}`);
  }
  const payload: unknown = await response.json();
  if (!isCurrencyRateList(payload)) {
    throw new Error(`GET ${CURRENCIES_PATH} returned an unexpected payload`);
  }
  return payload;
}

// The codes the ledger can be restated in. A rate is used only in the direction the rate
// table states it and is never composed through a third currency, so a pair whose
// from_currency is not the base converts nothing here, however much it looks like it
// should.
export function targetCurrencies(rates: CurrencyRate[]): string[] {
  const reachable = rates
    .filter((rate) => rate.from_currency === BASE_CURRENCY)
    .map((rate) => rate.to_currency)
    .filter((code) => code !== BASE_CURRENCY);
  return [BASE_CURRENCY, ...[...new Set(reachable)].sort((a, b) => a.localeCompare(b))];
}

export const currenciesQueryOptions = queryOptions({
  queryKey: ["currencies"],
  queryFn: ({ signal }) => fetchCurrencies(signal),
});
