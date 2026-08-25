import { createRootRoute, Link, Outlet } from "@tanstack/react-router";

export const Route = createRootRoute({ component: RootLayout });

// The shell every route renders inside: the slot the matched page fills.
function RootLayout() {
  // Neither link carries a search, so each page's validateSearch fills its own defaults
  // and crossing between them resets the currency. That is also why includeSearch is off:
  // it defaults to on, and a link with no search matches no URL that carries filters, so
  // the current tab would never mark itself. The path is the whole question here.
  const link = "btn btn-ghost btn-sm font-normal";
  // btn-active alone, and no second font weight: the type scale is two of them, and a
  // font-normal base against a font-semibold active would leave CSS order to decide.
  const active = { className: "btn-active" };
  const activeOptions = { exact: true, includeSearch: false };

  return (
    <div className="flex min-h-full flex-col">
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
          starts off the top of the screen. */}
      <main className="flex flex-1 flex-col items-center px-6 py-12">
        <Outlet />
      </main>
    </div>
  );
}
