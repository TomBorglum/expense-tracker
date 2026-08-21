import { createRootRoute, Outlet } from "@tanstack/react-router";

// The shell every route renders inside: the slot the matched page fills.
function RootLayout() {
  return (
    <div className="flex min-h-full flex-col">
      {/* A title bar, not navigation: one route means a nav would be dead UI. */}
      <header className="navbar bg-base-100 px-6 shadow-sm">
        <span className="text-xl font-semibold tracking-tight">Expense Tracker</span>
      </header>
      {/* Top-anchored rather than centred both ways: a long table centred vertically
          starts off the top of the screen. */}
      <main className="flex flex-1 flex-col items-center px-6 py-12">
        <Outlet />
      </main>
    </div>
  );
}

export const Route = createRootRoute({ component: RootLayout });
