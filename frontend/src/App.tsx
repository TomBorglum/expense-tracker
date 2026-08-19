import { Outlet } from "@tanstack/react-router";

// The shell every route renders inside: the slot the matched page fills.
export default function App() {
  return (
    <div className="flex min-h-full flex-col bg-slate-50 dark:bg-slate-900">
      {/* Top-anchored rather than centred both ways: a long table centred vertically
          starts off the top of the screen. */}
      <main className="flex flex-1 flex-col items-center px-6 py-16">
        <Outlet />
      </main>
    </div>
  );
}
