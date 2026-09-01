import { useQuery } from "@tanstack/react-query";
import {
  createFileRoute,
  retainSearchParams,
  type SearchSchemaInput,
  useNavigate,
} from "@tanstack/react-router";

import {
  BASE_CURRENCY,
  currenciesQueryOptions,
  targetCurrencies,
} from "../api/currencies";
import { CATEGORY_GROUPING, type TotalsQuery } from "../api/totals";
import { CategoryToggle } from "../components/CategoryToggle";
import { CurrencySelect } from "../components/CurrencySelect";
import { DateRangePicker } from "../components/DateRangePicker";
import { PeriodTotals } from "../components/PeriodTotals";
import { currentYear } from "../dates";

// The currency the totals are presented in, the days they are drawn from, and whether
// each period is split by category - carried in the URL so a view is shareable and
// survives a reload. An alias rather than a second declaration: the search is handed to
// totalsQueryOptions as it stands, so the two cannot drift.
export type TotalsSearch = TotalsQuery;

export const Route = createFileRoute("/totals")({
  component: TotalsPage,
  // The same three keys the expenses route retains, and for the same reason. group_by is
  // not among them: the expenses view declares no such parameter, so leaving here drops
  // the grouping and coming back starts ungrouped.
  search: {
    middlewares: [retainSearchParams(["currency", "from_date", "to_date"])],
  },
  // Supplies the default for an absent parameter and nothing else, like the expenses
  // route. A malformed code or date is handed on to the backend, which refuses it with a
  // 422. The date defaults read the clock, which is why the page tests pin it.
  validateSearch: (
    search: Record<string, unknown> & SearchSchemaInput,
  ): TotalsSearch => {
    const year = currentYear();
    return {
      currency: typeof search.currency === "string" ? search.currency : BASE_CURRENCY,
      from_date: typeof search.from_date === "string" ? search.from_date : year.from,
      to_date: typeof search.to_date === "string" ? search.to_date : year.to,
      // The one parameter with no default to fill in: absent means ungrouped here
      // exactly as it does on the wire, so the off state needs no value to carry it.
      group_by: search.group_by === CATEGORY_GROUPING ? CATEGORY_GROUPING : undefined,
    };
  },
});

function TotalsPage() {
  // Read whole rather than destructured: it is both what the controls display and what
  // the totals request, and each control navigates with the others left as they were.
  const search = Route.useSearch();
  const navigate = useNavigate();
  // The rate table is what the selector can offer. Its failure is not the totals': an
  // unreachable or empty one leaves the base currency, which needs no rate, and the
  // periods below still load.
  const rates = useQuery(currenciesQueryOptions);
  const options = rates.isSuccess ? targetCurrencies(rates.data) : [BASE_CURRENCY];

  return (
    // A link in the chain __root.tsx heads: a flex column rather than a block, block
    // layout having no shrink step to pass the bound on with.
    <div className="flex min-h-0 w-full max-w-4xl flex-col">
      <div className="flex flex-wrap items-center justify-between gap-4 pb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Totals</h1>
        <div className="flex flex-wrap items-center gap-6">
          <DateRangePicker
            from={search.from_date}
            to={search.to_date}
            onChange={(from, to) => {
              void navigate({
                to: "/totals",
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
              void navigate({ to: "/totals", search: { ...search, currency: next } });
            }}
          />
          <CategoryToggle
            checked={search.group_by !== undefined}
            onChange={(byCategory) => {
              void navigate({
                to: "/totals",
                search: {
                  ...search,
                  group_by: byCategory ? CATEGORY_GROUPING : undefined,
                },
              });
            }}
          />
        </div>
      </div>
      <section className="card min-h-0 bg-base-100 shadow-sm">
        <div className="card-body min-h-0">
          <PeriodTotals query={search} />
        </div>
      </section>
    </div>
  );
}
