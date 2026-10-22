import { useQuery } from "@tanstack/react-query";

import { CREDIT_CLASS, displayAmount } from "../amounts";
import {
  type RangeAverage,
  selectSummary,
  type TotalsQuery,
  totalsQueryOptions,
  ungrouped,
} from "../api/totals";

interface TotalsSummaryProps {
  readonly query: TotalsQuery;
}

const LABEL = "Average per month";

// daisyUI leaves .stats inline-grid with no background, so these are what make it span
// the page and carry the card colours the table's section beside it does. shrink-0
// because .stats sets overflow-x, which forces overflow-y to auto as well: squashed by a
// few pixels as a flex item, it would scroll a one-line figure. The table below is what
// the page's height bound is meant to shrink.
const STATS = "stats w-full shrink-0 bg-base-100 shadow-sm";
// .stat-title is 0.75rem, a size the page's scale does not have - the same undo the
// calendar, the nav tabs and the category fieldset each carry.
const TITLE = "stat-title text-sm";
// .stat-value is 2rem at weight 800, a fourth size and a third weight. text-2xl and
// font-semibold are both on the scale already.
const VALUE = "stat-value text-2xl font-semibold tabular-nums";

// A description list rather than daisyUI's divs: the label names the figure, so the two
// are a term and its definition and a reader is told which belongs to which. The div
// stays as the grid cell, which a dl may hold around each pair.
function Figure({ average }: { readonly average: RangeAverage }) {
  const shown = displayAmount(average.average);
  return (
    <div className="stat">
      <dt className={TITLE}>{LABEL}</dt>
      <dd className={`${VALUE} ${shown.isCredit ? CREDIT_CLASS : ""}`}>
        {shown.text} {average.currency}
      </dd>
    </div>
  );
}

// What the totals range averages to, above the periods it is drawn from. The figure
// arrives computed: the mean of the period totals over the calendar the rows span, which
// nothing here accumulates, for the reason PeriodTotals adds no amounts either. One stat
// per currency, which is one in practice because the view always asks for a currency.
export function TotalsSummary({ query }: TotalsSummaryProps) {
  // The grouping is dropped, so this is the key PeriodTotals already requests: the two
  // read one cache entry, and the category toggle changes nothing here. The summary is
  // the same either way, so there is nothing to switch on.
  const summary = useQuery({
    ...totalsQueryOptions(ungrouped(query)),
    select: selectSummary,
  });

  // Pending and failed both render nothing. PeriodTotals below owns the one spinner and
  // the one role="alert", and a second alert would announce one failure twice.
  if (!summary.isSuccess) {
    return null;
  }

  return (
    <dl className={STATS}>
      {summary.data.length === 0 ? (
        // A range holding nothing is a figure's absence, not an alert and not 0.00: it
        // recorded nothing, which is a different fact from netting to zero.
        <div className="stat">
          <dt className={TITLE}>{LABEL}</dt>
          <dd className="text-base-content/60">None recorded</dd>
        </div>
      ) : (
        summary.data.map((average) => (
          <Figure key={average.currency} average={average} />
        ))
      )}
    </dl>
  );
}
