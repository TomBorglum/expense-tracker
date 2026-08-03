import { useQuery } from "@tanstack/react-query";

import { greetingQueryOptions } from "./api/greeting";

// The greeting is owned by the Python package and served from /api/greeting, so the
// page fetches it at runtime instead of shipping its own copy of the wording.
function GreetingMessage() {
  // Not destructured: useQuery returns a discriminated union, and reading through the
  // result is what narrows `data` to a Greeting in the success branch below.
  const query = useQuery(greetingQueryOptions);

  if (query.isPending) {
    // <output> rather than role="status" on a <p>: it carries that role implicitly, so
    // spelling it out would be recreating semantics HTML already has (sonar S6819).
    // The error branch keeps its role - no element implies role="alert".
    return (
      <output className="text-4xl font-semibold tracking-tight text-slate-400 dark:text-slate-500">
        Loading...
      </output>
    );
  }

  if (query.isError) {
    return (
      <p
        role="alert"
        className="text-4xl font-semibold tracking-tight text-red-700 dark:text-red-400"
      >
        Could not load the greeting.
      </p>
    );
  }

  return (
    <h1 className="text-4xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
      {query.data.greeting}
    </h1>
  );
}

export default function App() {
  return (
    <main className="flex min-h-full items-center justify-center bg-slate-50 px-6 dark:bg-slate-900">
      <GreetingMessage />
    </main>
  );
}
