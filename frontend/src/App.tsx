// The greeting is owned by the Python package and baked in at build time, so the
// page needs no API call and Flask exposes no endpoint for it.
import greeting from "@data/greeting.json";

export default function App() {
  return (
    <main className="flex min-h-full items-center justify-center bg-slate-50 px-6 dark:bg-slate-900">
      <h1 className="text-4xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
        {greeting.greeting}
      </h1>
    </main>
  );
}
