import { useQuery } from "@tanstack/react-query";

import { type ExpensesQuery, expensesQueryOptions } from "../api/expenses";

interface ExpensesTableProps {
  readonly query: ExpensesQuery;
}

// The expenses are owned by the Python package and served from /api/expenses, newest
// first, restated in the currency asked for and narrowed to the days asked for. Amounts
// and dates are rendered exactly as they arrive: the backend sends amount as a string so
// no float round trip can drift a total by a cent - conversion included, which is why it
// happens there and not here - and the date is a bare YYYY-MM-DD, which new Date() would
// read as UTC and print a day early west of Greenwich.
export function ExpensesTable({ query }: ExpensesTableProps) {
  // Not destructured: useQuery returns a discriminated union, and reading through the
  // result is what narrows `data` to an Expense[] in the success branch below.
  const expenses = useQuery(expensesQueryOptions(query));

  if (expenses.isPending) {
    // <output> rather than role="status" on a <p>: it carries that role implicitly, so
    // spelling it out would be recreating semantics HTML already has (sonar S6819).
    // The error branch keeps its role - no element implies role="alert".
    return (
      <output className="flex items-center gap-3 text-sm text-base-content/60">
        <span className="loading loading-spinner loading-sm" />
        <span>Loading expenses...</span>
      </output>
    );
  }

  if (expenses.isError) {
    return (
      <div role="alert" className="alert alert-error">
        Could not load the expenses.
      </div>
    );
  }

  return (
    // The scroll port the chain in __root.tsx bounds, so the rows move and table-pin-rows
    // keeps the header row still. scrollbar-gutter-stable holds the columns still as a
    // widening date range crosses the point where the rows start overflowing. It needs no
    // min-h-0: a box whose overflow is not visible already has an automatic minimum of 0.
    <div className="scrollbar-gutter-stable overflow-auto">
      <table className="table table-pin-rows table-zebra">
        {/* The table's accessible name, which is how the tests reach it. Hidden from
            sight because the page already shows the same word as its heading. */}
        <caption className="sr-only">Expenses</caption>
        <thead>
          {/* font-semibold on every th, because daisyUI puts 600 on <thead> and the
              browser's own `th { font-weight: bold }` beats an inherited value. */}
          <tr>
            <th scope="col" className="text-right font-semibold">
              Amount
            </th>
            <th scope="col" className="font-semibold">
              Currency
            </th>
            <th scope="col" className="font-semibold">
              Date
            </th>
            <th scope="col" className="font-semibold">
              Category
            </th>
            <th scope="col" className="font-semibold">
              Details
            </th>
          </tr>
        </thead>
        <tbody>
          {expenses.data.length === 0 ? (
            // A database nobody has run the loader against yet answers 200 with [], which
            // is a working server rather than a fault, so it gets a row and not the alert
            // above.
            <tr>
              <td colSpan={5} className="text-base-content/60">
                No expenses loaded.
              </td>
            </tr>
          ) : (
            expenses.data.map((expense, index) => (
              // The payload carries no id, and schema.sql notes that the same amount, day,
              // currency, category and details can legitimately repeat, so position is a
              // row's only identity. The rows are rendered in arrival order and never
              // sorted or filtered here, which is what makes that identity stable.
              // eslint-disable-next-line @eslint-react/no-array-index-key -- see above
              <tr key={index}>
                <td className="text-right tabular-nums">{expense.amount}</td>
                <td>{expense.currency}</td>
                <td className="tabular-nums">{expense.date}</td>
                <td>{expense.category}</td>
                <td>{expense.details}</td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
