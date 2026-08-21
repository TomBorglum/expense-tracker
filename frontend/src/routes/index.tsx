import { useQuery } from "@tanstack/react-query";
import { createFileRoute, useNavigate } from "@tanstack/react-router";

import {
  BASE_CURRENCY,
  currenciesQueryOptions,
  targetCurrencies,
} from "../api/currencies";
import { type ExpensesQuery } from "../api/expenses";
import { CurrencySelect } from "../components/CurrencySelect";
import { DateRangePicker } from "../components/DateRangePicker";
import { ExpensesTable } from "../components/ExpensesTable";
import { currentMonth } from "../dates";

// The currency the expenses are presented in and the days they are drawn from, carried
// in the URL so a view is shareable and survives a reload. An alias rather than a second
// declaration: the search is handed to expensesQueryOptions as it stands, so the two
// cannot drift.
export type ExpensesSearch = ExpensesQuery;

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
});

function ExpensesPage() {
  // Read whole rather than destructured: it is both what the controls display and what
  // the table requests, and each control navigates with the others left as they were.
  const search = Route.useSearch();
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
