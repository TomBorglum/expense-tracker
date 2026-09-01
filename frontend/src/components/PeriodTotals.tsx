import { useQuery } from "@tanstack/react-query";

import {
  CATEGORY_GROUPING,
  type PeriodTotal,
  type TotalsQuery,
  totalsQueryOptions,
} from "../api/totals";

interface PeriodTotalsProps {
  readonly query: TotalsQuery;
}

// The category rows of one payload, keyed by the period they belong to. A row carrying no
// category is a period nobody spent in, which has nothing to list under it.
function categoriesByPeriod(totals: PeriodTotal[]): Map<string, PeriodTotal[]> {
  const grouped = new Map<string, PeriodTotal[]>();
  for (const total of totals) {
    if (total.category === undefined) {
      continue;
    }
    const rows = grouped.get(total.period);
    if (rows === undefined) {
      grouped.set(total.period, [total]);
    } else {
      rows.push(total);
    }
  }
  return grouped;
}

// Two rows differing only by currency are two rows, so neither key is the period alone.
// The UI always sends ?currency=, which collapses them, but the contract does not.
function rowKey(total: PeriodTotal): string {
  return `${total.period} ${total.category ?? ""} ${total.currency ?? ""}`;
}

// The period's row is the group's heading and carries the period's own total. border-b-0
// drops the border daisyUI puts between a band and the first category listed under it.
const PERIOD_BAND = "border-b-0 bg-base-200";
// The gap above a band, which is what separates two periods: daisyUI leaves .table on
// border-collapse: separate, so the border is the cell's own, and bg-clip-padding keeps
// bg-base-200 out of it, leaving the card to show through. All three are one mechanism.
const PERIOD_GAP = "bg-clip-padding border-t-8 border-t-transparent";

// The expenses of /api/expenses summed by month, newest first, restated in the currency
// asked for and narrowed to the days asked for. Amounts and the bounds each period was
// summed over are rendered exactly as they arrive: the backend sends amount as a string so
// no float round trip can drift a total by a cent, and the two dates are bare YYYY-MM-DD,
// which new Date() would read as UTC and print a day early west of Greenwich.
export function PeriodTotals({ query }: PeriodTotalsProps) {
  // Destructured out rather than overwritten with undefined, so the ungrouped query key
  // holds no dead entry.
  const { group_by: grouping, ...range } = query;
  const byCategory = grouping !== undefined;
  // The ungrouped payload is the month total itself, straight from the backend. Adding
  // the category rows up here instead would be arithmetic on amounts this side of the
  // wire, which is the thing sending them as strings exists to avoid.
  const totals = useQuery(totalsQueryOptions(range));
  const breakdownQuery = useQuery({
    ...totalsQueryOptions({ ...range, group_by: CATEGORY_GROUPING }),
    enabled: byCategory,
  });
  // The one place the grouping is consulted. enabled stops the request but evicts
  // nothing, so a disabled query goes on serving whatever it last fetched and stays
  // pending only until it has: an ungrouped render must have no path to that result
  // rather than merely decline to use it.
  const breakdown = byCategory ? breakdownQuery : undefined;

  if (totals.isPending || breakdown?.isPending) {
    // <output> rather than role="status" on a <p>: it carries that role implicitly (sonar
    // S6819). The error branch keeps its role - no element implies role="alert".
    return (
      <output className="flex items-center gap-3 text-sm text-base-content/60">
        <span className="loading loading-spinner loading-sm" />
        <span>Loading totals...</span>
      </output>
    );
  }

  if (totals.isError || breakdown?.isError) {
    return (
      <div role="alert" className="alert alert-error">
        Could not load the totals.
      </div>
    );
  }

  const categories = breakdown?.isSuccess
    ? categoriesByPeriod(breakdown.data)
    : new Map<string, PeriodTotal[]>();

  return (
    <div className="overflow-x-auto">
      {/* No table-zebra: the stripes run per row and would cut across the period groups
          rather than with them. */}
      <table className="table table-fixed min-w-md">
        {/* The columns are pinned so the category toggle only adds and removes rows:
            daisyUI leaves table-layout auto, where each view's own rows size the
            columns and the leftover is re-spread across them, so the amounts land at a
            different x in each. min-w-md is what the wrapper's overflow-x-auto scrolls
            once a fixed layout has no room left to take from the first column. */}
        <colgroup>
          <col />
          <col className="w-40" />
          <col className="w-24" />
        </colgroup>
        {/* The table's accessible name, which is how the tests reach it. Hidden from sight
            because the page already shows the same word as its heading. */}
        <caption className="sr-only">Totals</caption>
        {/* No thead: the first column holds a period's bounds on the band rows and a
            category on the lines under them, so no column header is true for every row.
            The rowgroup and row headers below are what give each amount its
            association. */}
        {totals.data.length === 0 ? (
          <tbody>
            <tr>
              {/* An expense table nobody has run the loader against yet answers 200 with
                  [], and so does a range nothing falls inside. Both are a working server
                  rather than a fault, so this is a row and not the alert above. */}
              <td colSpan={3} className="text-base-content/60">
                No expenses in this range.
              </td>
            </tr>
          </tbody>
        ) : (
          totals.data.map((total, index) => {
            const band = index === 0 ? PERIOD_BAND : `${PERIOD_BAND} ${PERIOD_GAP}`;
            return (
              <tbody key={rowKey(total)}>
                <tr>
                  <th
                    scope="rowgroup"
                    className={`${band} text-left font-semibold tabular-nums`}
                  >
                    {total.from_date} to {total.to_date}
                  </th>
                  {total.amount === undefined ? (
                    // Absent, not "0.00": a month of refunds can genuinely net to zero,
                    // and that is a different fact from having recorded nothing.
                    <td
                      colSpan={2}
                      className={`${band} text-right text-base-content/60`}
                    >
                      None recorded
                    </td>
                  ) : (
                    <>
                      <td className={`${band} text-right font-semibold tabular-nums`}>
                        {total.amount}
                      </td>
                      <td className={band}>{total.currency}</td>
                    </>
                  )}
                </tr>
                {(categories.get(total.period) ?? []).map((row) => (
                  <tr key={rowKey(row)}>
                    <th scope="row" className="pl-8 font-normal">
                      {row.category}
                    </th>
                    <td className="text-right tabular-nums">{row.amount}</td>
                    <td>{row.currency}</td>
                  </tr>
                ))}
              </tbody>
            );
          })
        )}
      </table>
    </div>
  );
}
