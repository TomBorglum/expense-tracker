import { createRootRoute, Link, Outlet } from "@tanstack/react-router";

export const Route = createRootRoute({ component: RootLayout });

// The shell every route renders inside: the slot the matched page fills.
function RootLayout() {
  // Neither link carries a search, so each page's validateSearch fills its own defaults
  // and crossing between them resets the currency. That is also why includeSearch is off:
  // it defaults to on, and a link with no search matches no URL that carries filters, so
  // the current tab would never mark itself. The path is the whole question here.
  // btn-sm writes 0.75rem, one step below the page; text-sm brings the tabs back to
  // the 0.875rem the captions, the controls and the table use.
  const link = "btn btn-ghost btn-sm text-sm font-normal";
  // btn-active alone, and no second font weight: the type scale is two of them, and a
  // font-normal base against a font-semibold active would leave CSS order to decide.
  const active = { className: "btn-active" };
  const activeOptions = { exact: true, includeSearch: false };

  return (
    <div className="flex h-full flex-col">
      <header className="navbar bg-base-100 px-6 shadow-sm">
        <span className="text-xl font-semibold tracking-tight">Expense Tracker</span>
        <nav className="ml-auto flex items-center gap-1">
          <Link
            to="/"
            className={link}
            activeProps={active}
            activeOptions={activeOptions}
          >
            Expenses
          </Link>
          <Link
            to="/totals"
            className={link}
            activeProps={active}
            activeOptions={activeOptions}
          >
            Totals
          </Link>
        </nav>
      </header>
      {/* Top-anchored rather than centred both ways: a long table centred vertically
          starts off the top of the screen.

          min-h-0 heads the chain that bounds each page's table, and is needed despite
          flex-1: a flex item's automatic minimum size floors its used height at its
          content height even when it is growing from a zero basis. Every flex column
          from here down to a table's overflow-auto wrapper carries one, and none carries
          flex-1; miss one and the window scrolls again, add a flex-1 and a two-row table
          fills the screen. */}
      <main className="flex min-h-0 flex-1 flex-col items-center px-6 py-12">
        <Outlet />
      </main>
    </div>
  );
}
