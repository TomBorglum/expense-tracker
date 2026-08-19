import { ExpensesTable } from "../components/ExpensesTable";

export default function ExpensesPage() {
  return (
    <div className="w-full max-w-4xl">
      <h1 className="pb-6 text-3xl font-semibold tracking-tight">Expenses</h1>
      <section className="card bg-base-100 shadow-sm">
        <div className="card-body">
          <ExpensesTable />
        </div>
      </section>
    </div>
  );
}
