import { useQuery } from "@tanstack/react-query";
import {
  createFileRoute,
  retainSearchParams,
  type SearchSchemaInput,
  useNavigate,
} from "@tanstack/react-router";

import {
  categoriesQueryOptions,
  categoryFilter,
  categoryNames,
} from "../api/categories";
import {
  BASE_CURRENCY,
  currenciesQueryOptions,
  targetCurrencies,
} from "../api/currencies";
import { type ExpensesQuery } from "../api/expenses";
import { CategoryPicker } from "../components/CategoryPicker";
import { CurrencySelect } from "../components/CurrencySelect";
import { DateRangePicker } from "../components/DateRangePicker";
import { ExpensesTable } from "../components/ExpensesTable";
import { currentYear } from "../dates";

// The currency the expenses are presented in, the days they are drawn from and the
// categories they are narrowed to, carried in the URL so a view is shareable and
// survives a reload. An alias rather than a second declaration: the search is handed to
// expensesQueryOptions as it stands, so the two cannot drift.
export type ExpensesSearch = ExpensesQuery;

export const Route = createFileRoute("/")({
  component: ExpensesPage,
  // What crossing to /totals brings along, the links in __root.tsx carrying no search of
  // their own. Retained rather than re-defaulted: without this the currency, the range
  // and the categories are picked again on every switch between the two views. group_by
  // is deliberately not here - it is declared on /totals alone, and this view means
  // nothing by it.
  search: {
    middlewares: [retainSearchParams(["currency", "from_date", "to_date", "category"])],
  },
  // Supplies the default for an absent parameter and nothing else. A malformed code,
  // date or category is handed on to the backend, which refuses it with a 422;
  // re-checking any here would put the pattern in conversion.py, date_range.py or
  // category_filter.py in a second place to drift from. The date defaults read the
  // clock, which is why the page tests pin it.
  validateSearch: (
    search: Record<string, unknown> & SearchSchemaInput,
  ): ExpensesSearch => {
    const year = currentYear();
    return {
      currency: typeof search.currency === "string" ? search.currency : BASE_CURRENCY,
      from_date: typeof search.from_date === "string" ? search.from_date : year.from,
      to_date: typeof search.to_date === "string" ? search.to_date : year.to,
      category: categoryFilter(search.category),
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
  // The category list is what the picker can offer, on the same terms as the rates: its
  // failure disables the control and nothing else.
  const categories = useQuery(categoriesQueryOptions);
  const categoryOptions = categories.isSuccess ? categoryNames(categories.data) : [];

  return (
    // A link in the chain __root.tsx heads: a flex column rather than a block, block
    // layout having no shrink step to pass the bound on with.
    <div className="flex min-h-0 w-full max-w-4xl flex-col">
      <div className="flex flex-wrap items-center justify-between gap-4 pb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Expenses</h1>
        <div className="flex flex-wrap items-center gap-6">
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
          <CategoryPicker
            selected={search.category ?? []}
            options={categoryOptions}
            disabled={categoryOptions.length === 0}
            onChange={(next) => {
              // Undefined rather than [], so an emptied selection leaves the URL and
              // the request the way an absent parameter does.
              void navigate({
                to: "/",
                search: { ...search, category: next.length === 0 ? undefined : next },
              });
            }}
          />
        </div>
      </div>
      <section className="card min-h-0 bg-base-100 shadow-sm">
        <div className="card-body min-h-0">
          <ExpensesTable query={search} />
        </div>
      </section>
    </div>
  );
}
