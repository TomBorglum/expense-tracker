import {
  createFileRoute,
  retainSearchParams,
  type SearchSchemaInput,
  useNavigate,
} from "@tanstack/react-router";

import { CATEGORY_GROUPING, type TotalsQuery } from "../api/totals";
import { CategoryToggle } from "../components/CategoryToggle";
import { ExpenseFilters } from "../components/ExpenseFilters";
import { PeriodTotals } from "../components/PeriodTotals";
import { SHARED_SEARCH_KEYS, sharedSearch } from "../search";

// The currency the totals are presented in, the days they are drawn from, the categories
// they are narrowed to, and whether each period is split by category - carried in the
// URL so a view is shareable and survives a reload. An alias rather than a second
// declaration: the search is handed to totalsQueryOptions as it stands, so the two
// cannot drift.
export type TotalsSearch = TotalsQuery;

export const Route = createFileRoute("/totals")({
  component: TotalsPage,
  // group_by is not retained: the expenses view declares no such parameter, so leaving
  // here drops the grouping and coming back starts ungrouped.
  search: { middlewares: [retainSearchParams(SHARED_SEARCH_KEYS)] },
  validateSearch: (
    search: Record<string, unknown> & SearchSchemaInput,
  ): TotalsSearch => ({
    ...sharedSearch(search),
    // The one parameter with no default to fill in: absent means ungrouped here exactly
    // as it does on the wire, so the off state needs no value to carry it.
    group_by: search.group_by === CATEGORY_GROUPING ? CATEGORY_GROUPING : undefined,
  }),
});

function TotalsPage() {
  // Read whole rather than destructured: it is both what the controls display and what
  // the totals request, and each control navigates with the others left as they were.
  const search = Route.useSearch();
  const navigate = useNavigate();

  return (
    // A link in the chain __root.tsx heads: a flex column rather than a block, block
    // layout having no shrink step to pass the bound on with.
    <div className="flex min-h-0 w-full max-w-4xl flex-col">
      <div className="flex flex-wrap items-center justify-between gap-4 pb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Totals</h1>
        <ExpenseFilters
          search={search}
          onChange={(next) => {
            // Voided rather than awaited: navigate returns a promise nothing here
            // needs, and an unhandled one fails the lint.
            void navigate({ to: "/totals", search: { ...search, ...next } });
          }}
        >
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
        </ExpenseFilters>
      </div>
      <section className="card min-h-0 bg-base-100 shadow-sm">
        <div className="card-body min-h-0">
          <PeriodTotals query={search} />
        </div>
      </section>
    </div>
  );
}
