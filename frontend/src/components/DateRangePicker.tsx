import { type DateRange, DayPicker } from "@daypicker/react";
import { useState } from "react";

import { fromIsoDate, toIsoDate } from "../dates";

interface DateRangePickerProps {
  readonly from: string;
  readonly to: string;
  readonly onChange: (from: string, to: string) => void;
}

// The days the expenses are drawn from, as the two YYYY-MM-DD strings the API reads. A
// value the backend would refuse is shown as it stands rather than corrected, the way
// CurrencySelect shows a code it was given.
export function DateRangePicker({ from, to, onChange }: DateRangePickerProps) {
  const [open, setOpen] = useState(false);
  // Holds the half-built range between the two clicks. Null while the calendar agrees
  // with the URL, which is what makes the props the source of truth the rest of the time.
  const [picked, setPicked] = useState<DateRange | null>(null);
  const selected = picked ?? { from: fromIsoDate(from), to: fromIsoDate(to) };

  function handleSelect(next: DateRange | undefined) {
    if (next?.from && next.to) {
      setPicked(null);
      setOpen(false);
      onChange(toIsoDate(next.from), toIsoDate(next.to));
      return;
    }
    // Only a start so far. Reporting it would put an open-ended range in the URL, and
    // the backend reads an empty bound as malformed rather than as no bound.
    setPicked(next ?? null);
  }

  return (
    <div className="flex items-center gap-3">
      <span id="date-range-label" className="text-sm text-base-content/60">
        Dates
      </span>
      {/* Positioned by hand rather than with daisyUI's dropdown classes. Those hide
          .dropdown-content until :focus-within or :popover-open, which fights a panel
          whose open state is React's - the calendar would vanish the moment focus left
          it while still mounted. jsdom evaluates no CSS, so no test sees this. */}
      <div className="relative">
        {/* Labelled by the caption and by itself, so the accessible name carries both
            the control's purpose and the range it currently shows. */}
        <button
          id="date-range-value"
          type="button"
          aria-expanded={open}
          aria-labelledby="date-range-label date-range-value"
          className="btn btn-outline btn-sm font-normal tabular-nums"
          onClick={() => {
            setOpen(!open);
          }}
        >
          {from} to {to}
        </button>
        {open && (
          <div className="absolute top-full right-0 z-10 mt-2 rounded-box bg-base-100 p-2 shadow-lg">
            {/* resetOnSelect, because the range arriving from the URL is always
                complete: without it a click would drag one end instead of starting
                over. Neither it nor addToRange can produce a range that ends before it
                begins, which is why no bound is passed. */}
            <DayPicker
              mode="range"
              resetOnSelect
              defaultMonth={fromIsoDate(from)}
              selected={selected}
              onSelect={handleSelect}
            />
          </div>
        )}
      </div>
    </div>
  );
}
