import {
  createFileRoute,
  retainSearchParams,
  type SearchSchemaInput,
  useNavigate,
} from "@tanstack/react-router";

import { type ExpensesQuery } from "../api/expenses";
import { ExpenseFilters } from "../components/ExpenseFilters";
import { ExpensesTable } from "../components/ExpensesTable";
import { SHARED_SEARCH_KEYS, sharedSearch } from "../search";

// The currency the expenses are presented in, the days they are drawn from and the
// categories they are narrowed to, carried in the URL so a view is shareable and
// survives a reload. An alias rather than a second declaration: the search is handed to
// expensesQueryOptions as it stands, so the two cannot drift.
export type ExpensesSearch = ExpensesQuery;

export const Route = createFileRoute("/")({
  component: ExpensesPage,
  search: { middlewares: [retainSearchParams(SHARED_SEARCH_KEYS)] },
  validateSearch: (
    search: Record<string, unknown> & SearchSchemaInput,
  ): ExpensesSearch => sharedSearch(search),
});

function ExpensesPage() {
  // Read whole rather than destructured: it is both what the controls display and what
  // the table requests, and each control navigates with the others left as they were.
  const search = Route.useSearch();
  const navigate = useNavigate();

  return (
    // A link in the chain __root.tsx heads: a flex column rather than a block, block
    // layout having no shrink step to pass the bound on with.
    <div className="flex min-h-0 w-full max-w-4xl flex-col">
      <div className="flex flex-wrap items-center justify-between gap-4 pb-6">
        <h1 className="text-2xl font-semibold tracking-tight">Expenses</h1>
        <ExpenseFilters
          search={search}
          onChange={(next) => {
            // Voided rather than awaited: navigate returns a promise nothing here
            // needs, and an unhandled one fails the lint.
            void navigate({ to: "/", search: { ...search, ...next } });
          }}
        />
      </div>
      <section className="card min-h-0 bg-base-100 shadow-sm">
        <div className="card-body min-h-0">
          <ExpensesTable query={search} />
        </div>
      </section>
    </div>
  );
}
