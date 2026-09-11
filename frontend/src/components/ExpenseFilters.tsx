import { useQuery } from "@tanstack/react-query";
import { type ReactNode } from "react";

import { categoriesQueryOptions, categoryNames } from "../api/categories";
import {
  BASE_CURRENCY,
  currenciesQueryOptions,
  targetCurrencies,
} from "../api/currencies";
import { type ExpensesQuery } from "../api/expenses";
import { CategoryPicker } from "./CategoryPicker";
import { CurrencySelect } from "./CurrencySelect";
import { DateRangePicker } from "./DateRangePicker";

interface ExpenseFiltersProps {
  readonly search: ExpensesQuery;
  // The part of the search a control changed, for the route to spread over the rest:
  // every navigate carries the whole search, because validateSearch re-defaults an
  // absent parameter.
  readonly onChange: (next: Partial<ExpensesQuery>) => void;
  // What a view adds after the shared three, the totals' grouping toggle.
  readonly children?: ReactNode;
}

// The three controls both views share, reading the URL they are given and reporting
// the one part a control changed. Router-free like everything else here: the route
// owns the navigate, this owns the requests the options come from.
export function ExpenseFilters({ search, onChange, children }: ExpenseFiltersProps) {
  // The rate table is what the selector can offer. Its failure is not the table's: an
  // unreachable or empty one leaves the base currency, which needs no rate, and the
  // expenses below still load.
  const rates = useQuery(currenciesQueryOptions);
  const options = rates.isSuccess ? targetCurrencies(rates.data) : [BASE_CURRENCY];
  // The category list is what the picker can offer, on the same terms as the rates: its
  // failure disables the control and nothing else.
  const categories = useQuery(categoriesQueryOptions);
  const categoryOptions = categories.isSuccess ? categoryNames(categories.data) : [];

  return (
    <div className="flex flex-wrap items-center gap-6">
      <DateRangePicker
        from={search.from_date}
        to={search.to_date}
        onChange={(from, to) => {
          onChange({ from_date: from, to_date: to });
        }}
      />
      <CurrencySelect
        value={search.currency}
        options={options}
        disabled={!rates.isSuccess}
        onChange={(next) => {
          onChange({ currency: next });
        }}
      />
      <CategoryPicker
        selected={search.category ?? []}
        options={categoryOptions}
        disabled={categoryOptions.length === 0}
        onChange={(next) => {
          // Undefined rather than [], so an emptied selection leaves the URL and the
          // request the way an absent parameter does.
          onChange({ category: next.length === 0 ? undefined : next });
        }}
      />
      {children}
    </div>
  );
}
