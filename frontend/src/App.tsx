import { Link, Outlet } from "@tanstack/react-router";

// The shell every route renders inside: the nav, and the slot the matched page fills.
export default function App() {
  return (
    <div className="flex min-h-full flex-col bg-slate-50 dark:bg-slate-900">
      <nav className="flex gap-6 border-b border-slate-200 px-6 py-4 text-sm text-slate-600 dark:border-slate-800 dark:text-slate-400">
        <Link
          to="/"
          activeOptions={{ exact: true }}
          activeProps={{
            className: "font-semibold text-slate-900 dark:text-slate-100",
          }}
        >
          Greeting
        </Link>
        <Link
          to="/expenses"
          activeProps={{
            className: "font-semibold text-slate-900 dark:text-slate-100",
          }}
        >
          Expenses
        </Link>
      </nav>
      {/* Top-anchored rather than centred both ways: a long table centred vertically
          starts off the top of the screen. */}
      <main className="flex flex-1 flex-col items-center px-6 py-16">
        <Outlet />
      </main>
    </div>
  );
}
