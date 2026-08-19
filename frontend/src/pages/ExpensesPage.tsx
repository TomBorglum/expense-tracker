import { ExpensesTable } from "../components/ExpensesTable";

export default function ExpensesPage() {
  return (
    <div className="w-full max-w-3xl">
      <h1 className="pb-8 text-4xl font-semibold tracking-tight text-slate-900 dark:text-slate-100">
        Expenses
      </h1>
      <ExpensesTable />
    </div>
  );
}
