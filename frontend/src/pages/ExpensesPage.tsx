import { useQuery } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";

import {
  BASE_CURRENCY,
  currenciesQueryOptions,
  targetCurrencies,
} from "../api/currencies";
import { CurrencySelect } from "../components/CurrencySelect";
import { DateRangePicker } from "../components/DateRangePicker";
import { ExpensesTable } from "../components/ExpensesTable";

// By path rather than by importing the route: router.ts imports this module, so the
// reverse import would be a cycle. The Register declaration at the foot of router.ts is
// what keeps this typed.
const routeApi = getRouteApi("/");

export default function ExpensesPage() {
  // Read whole rather than destructured: it is both what the controls display and what
  // the table requests, and each control navigates with the others left as they were.
  const search = routeApi.useSearch();
  const navigate = useNavigate();
  // The rate table is what the selector can offer. Its failure is not the table's: an
  // unreachable or empty one leaves the base currency, which needs no rate, and the
  // expenses below still load.
  const rates = useQuery(currenciesQueryOptions);
  const options = rates.isSuccess ? targetCurrencies(rates.data) : [BASE_CURRENCY];

  return (
    <div className="w-full max-w-4xl">
      <div className="flex flex-wrap items-center justify-between gap-4 pb-6">
        <h1 className="text-3xl font-semibold tracking-tight">Expenses</h1>
        <div className="flex flex-wrap items-center gap-4">
          <DateRangePicker
            from={search.from_date}
            to={search.to_date}
            onChange={(from, to) => {
              void navigate({
                to: "/",
                search: { ...search, from_date: from, to_date: to },
              });
            }}
          />
          <CurrencySelect
            value={search.currency}
            options={options}
            disabled={!rates.isSuccess}
            onChange={(next) => {
              // Voided rather than awaited: navigate returns a promise nothing here
              // needs, and an unhandled one fails the lint.
              void navigate({ to: "/", search: { ...search, currency: next } });
            }}
          />
        </div>
      </div>
      <section className="card bg-base-100 shadow-sm">
        <div className="card-body">
          <ExpensesTable query={search} />
        </div>
      </section>
    </div>
  );
}
