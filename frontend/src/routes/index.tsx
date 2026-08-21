import { useQuery } from "@tanstack/react-query";
import { createFileRoute, retainSearchParams } from "@tanstack/react-router";

import {
  BASE_CURRENCY,
  currenciesQueryOptions,
  targetCurrencies,
} from "../api/currencies";
import { type ExpensesQuery, expensesQueryOptions } from "../api/expenses";
import { CurrencySelect } from "../components/CurrencySelect";
import { DateRangePicker } from "../components/DateRangePicker";
import { ExpensesTable } from "../components/ExpensesTable";
import { currentMonth } from "../dates";

// The currency the expenses are presented in and the days they are drawn from, carried
// in the URL so a view is shareable and survives a reload. An alias rather than a second
// declaration: the search is handed to expensesQueryOptions as it stands, so the two
// cannot drift.
type ExpensesSearch = ExpensesQuery;

export const Route = createFileRoute("/")({
  component: ExpensesPage,
  // Supplies the default for an absent parameter and nothing else. A malformed code or
  // date is handed on to the backend, which refuses it with a 422; re-checking either
  // here would put the pattern in conversion.py or date_range.py in a second place to
  // drift from. The date defaults read the clock, which is why the page tests pin it.
  validateSearch: (search: Record<string, unknown>): ExpensesSearch => {
    const month = currentMonth();
    return {
      currency: typeof search.currency === "string" ? search.currency : BASE_CURRENCY,
      from_date: typeof search.from_date === "string" ? search.from_date : month.from,
      to_date: typeof search.to_date === "string" ? search.to_date : month.to,
    };
  },
  search: {
    // Carries all three across every navigation, so a call that names one parameter
    // keeps the other two rather than having them re-defaulted out from under it.
    middlewares: [retainSearchParams(["currency", "from_date", "to_date"])],
  },
  loaderDeps: ({ search }) => search,
  // prefetchQuery rather than ensureQueryData: it settles its own rejection, so a failed
  // request stays the table's alert instead of becoming the root route's errorComponent.
  // Not awaited either, so the page renders its pending state on the first tick and the
  // request ExpensesTable subscribes to is the one already in flight.
  loader: ({ context, deps }) => {
    void context.queryClient.prefetchQuery(expensesQueryOptions(deps));
  },
});

function ExpensesPage() {
  // Read whole rather than destructured: it is both what the controls display and what
  // the table requests, and each control navigates with the others left as they were.
  const search = Route.useSearch();
  // Scoped to this route, which is what gives the relative "." below a from to resolve
  // against.
  const navigate = Route.useNavigate();
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
                to: ".",
                search: (prev) => ({ ...prev, from_date: from, to_date: to }),
              });
            }}
          />
          <CurrencySelect
            value={search.currency}
            options={options}
            disabled={!rates.isSuccess}
            onChange={(next) => {
              // The updater form rather than a spread of the search read at render, so
              // the parameters kept are the ones current when the navigation happens.
              // Voided rather than awaited: navigate returns a promise nothing here
              // needs, and an unhandled one fails the lint.
              void navigate({
                to: ".",
                search: (prev) => ({ ...prev, currency: next }),
              });
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
