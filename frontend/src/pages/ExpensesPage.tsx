import { useQuery } from "@tanstack/react-query";
import { getRouteApi, useNavigate } from "@tanstack/react-router";

import {
  BASE_CURRENCY,
  currenciesQueryOptions,
  targetCurrencies,
} from "../api/currencies";
import { CurrencySelect } from "../components/CurrencySelect";
import { ExpensesTable } from "../components/ExpensesTable";

// By path rather than by importing the route: router.ts imports this module, so the
// reverse import would be a cycle. The Register declaration at the foot of router.ts is
// what keeps this typed.
const routeApi = getRouteApi("/");

export default function ExpensesPage() {
  const { currency } = routeApi.useSearch();
  const navigate = useNavigate();
  // The rate table is what the selector can offer. Its failure is not the table's: an
  // unreachable or empty one leaves the base currency, which needs no rate, and the
  // expenses below still load.
  const rates = useQuery(currenciesQueryOptions);
  const options = rates.isSuccess ? targetCurrencies(rates.data) : [BASE_CURRENCY];

  return (
    <div className="w-full max-w-4xl">
      <div className="flex items-center justify-between pb-6">
        <h1 className="text-3xl font-semibold tracking-tight">Expenses</h1>
        <CurrencySelect
          value={currency}
          options={options}
          disabled={!rates.isSuccess}
          onChange={(next) => {
            // Voided rather than awaited: navigate returns a promise nothing here needs,
            // and an unhandled one fails the lint.
            void navigate({ to: "/", search: { currency: next } });
          }}
        />
      </div>
      <section className="card bg-base-100 shadow-sm">
        <div className="card-body">
          <ExpensesTable currency={currency} />
        </div>
      </section>
    </div>
  );
}
